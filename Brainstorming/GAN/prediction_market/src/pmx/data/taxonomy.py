"""The tag taxonomy and the deterministic tagger (CONTRACTS_V2 7.14, decisions D-S6, D-S8, D-S9, D-S14).

``tags`` used to be a raw dump of provider labels: 201 distinct values over the 287 markets of the first
real build, the most frequent a Kalshi series ticker seen sixteen times, and 58 markets whose only tag
repeated their own category (``docs/REVIEW_2026-09-09_SCALE_TAGS.md``). A field like that cannot group
markets for a comparison, and a comparison is what the cohort of 18.5 exists for. So this module ships a
**controlled vocabulary** with three facets and a tagger that assigns them:

* ``subject``, one to four values in **tagger precedence order** (the first is the primary subject and
  therefore the cohort key);
* ``structure``, exactly one, the shape of the question;
* ``horizon``, exactly one, **derived from the market's declared life** (``close_at_ms -
  created_at_ms``) and never from provider text, never from ``resolved_at_ms``.

The raw provider strings do not disappear, they move to ``provider_labels`` (7.2): never a cohort key,
never displayed as a tag, kept so a reviewer can see what the provider said.

**The tagger is never a model call** (ruling R267, architecture rule 12 of ruling R245). Nothing here
imports ``pmx.gateway`` or ``pmx.llm``, nothing opens a socket, nothing reads a clock and nothing draws a
random number in the tagging path. The reason is in the contract: a tag decides which cohort a market
lands in, so a tag that moved between two rebuilds would move a claim. The two lexicon files are copied
**into** the dataset at ``taxonomy/tags.v1.json`` and ``taxonomy/kalshi_series_facets.v1.json``, inside
the walk of 4.3 and therefore inside ``dataset_hash``, so a vocabulary edit moves the hash rather than
silently re-cutting the cohorts of an existing dataset.

**A tag cannot leak** (7.9). :func:`tag_market` takes a :class:`TaggableMarket`, a protocol that declares
the seven fields it may read and no other: the question, the provider and its id, the market's declared
life and its raw provider labels. All of them exist before the market's first bar. ``resolution``,
``resolved_at_ms``, ``final_price_bp``, ``quality`` and the bars are not reachable through it, which is
what ``tests/test_taxonomy.py`` proves by handing it a market whose leak fields are poisoned and checking
the facets do not move.

**Coverage is measured per venue, not globally** (ruling R268 in the form decision D-S14 corrected). A
single 95 percent bar is unreachable on Manifold by construction: its question distribution has no dense
templates (a Chainsaw Man announcement, a Fooming Shoggoths song, the word count of a papal encyclical),
so its ``other`` bucket is large, is **reported** rather than hidden, and labels Manifold and only
Manifold ``taxonomy: "weak"``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from pmx.cohorts import (
    COHORT_MIN_TRAIN,
    SUBJECT_PLATFORM_META,
    VALUE_OTHER,
    Cohort,
    cohort_size_histogram,
)
from pmx.data.news.linker import (
    AUDIT_HASH_PREFIX,
    AUDIT_SUBSTREAM,
    AUDIT_VERDICTS,
    AUDITS_DIR,
    audit_dir_for,
    load_stopwords,
)
from pmx.errors import InvalidConfigError, SchemaError
from pmx.rng import RngTree, sample_without_replacement
from pmx.types import MS_PER_DAY, round_half_up, sha256_hex

__all__ = [
    "BUILDER_LABELS",
    "FACET_SOURCE_KEYWORDS",
    "FACET_SOURCE_OTHER",
    "FACET_SOURCE_SERIES",
    "FACET_SOURCES",
    "HORIZONS",
    "HORIZON_BOUNDS_MS",
    "LABEL_FORECASTABLE",
    "PROVIDER_LABELS_MAX",
    "RE_FACET_VALUE",
    "SERIES_FACETS_FILE",
    "SUBJECTS_MAX",
    "TAGS_FILE",
    "TAGS_MAX",
    "TAXONOMY_AUDIT_FILE",
    "TAXONOMY_AUDIT_N",
    "TAXONOMY_COVERAGE_MIN_PERMILLE",
    "TAXONOMY_DIR",
    "TAXONOMY_LABEL_OK",
    "TAXONOMY_LABEL_WEAK",
    "TAXONOMY_MIN_USABLE_COHORTS",
    "TAXONOMY_WEAK_LABEL",
    "Facets",
    "SeriesFacets",
    "TaggableMarket",
    "TaggedMarket",
    "TagLexicon",
    "TaxonomyAudit",
    "TaxonomyVerdict",
    "VenueTaxonomy",
    "apply_facets",
    "check_tags",
    "copy_lexicons",
    "horizon_of",
    "lexicon_sha256",
    "load_series_facets",
    "load_tag_lexicon",
    "provider_labels_of",
    "sample_taxonomy_audit",
    "series_ticker_of",
    "tag_market",
    "tags_of",
    "taxonomy_audit_from_dict",
    "taxonomy_audit_path",
    "taxonomy_block",
    "tokens_of",
    "venue_taxonomy",
]

# --------------------------------------------------------------------------------------------------
# Where the vocabulary lives and what it is called
# --------------------------------------------------------------------------------------------------
#: The lexicons live inside the package for the reason ruling R94 moved the others there: they are read
#: at run time, and a path relative to the repository root does not exist in an installed wheel.
#: ``parents[2]`` is ``src/pmx`` from ``src/pmx/data/taxonomy.py``.
LEXICON_DIR: Final = Path(__file__).resolve().parents[1] / "lexicons"
TAGS_FILE: Final = "tags.v1.json"
SERIES_FACETS_FILE: Final = "kalshi_series_facets.v1.json"

#: The directory the two files are copied into inside a dataset (7.8): inside the walk of 4.3, so both
#: are covered by ``dataset_hash``.
TAXONOMY_DIR: Final = "taxonomy"

#: The vocabulary version this module can read. A ``tags.v2`` is a new file and a new dataset hash
#: (ruling R301), never an edit to ``tags.v1.json``.
TAGS_VERSION: Final = "tags.v1"

# --------------------------------------------------------------------------------------------------
# The facet vocabulary's fixed parts
# --------------------------------------------------------------------------------------------------
#: A facet value: a lowercase slug (18.7's identifier table).
RE_FACET_VALUE: Final = re.compile(r"^[a-z][a-z0-9-]{0,31}$")

#: A ``tags`` or ``provider_labels`` entry (7.2). Wider than a facet value, because a provider label is
#: the provider's own string and may carry an underscore.
RE_TAG_VALUE: Final = re.compile(r"^[a-z0-9_-]{1,32}$")

#: The tokens the keyword rules match against: the lowercase alphabetic tokens of the question, of any
#: length. Length is **not** filtered here as it is in the linker's ``K`` of 7.6, because "cpi", "gpu",
#: "btc", "fed" and "oil" are exactly the tokens a subject rule needs. The stop list of 7.6 is applied,
#: which is what 7.14 asks for.
TOKEN_RE: Final = re.compile(r"[a-z]+")

#: The horizon facet, in order, and the exclusive upper bound of each in milliseconds (7.14). Ruling
#: R301: these four boundaries are part of ``tags.v1``, so moving one is a new lexicon version and a new
#: dataset hash and never an edit in place.
HORIZON_INTRADAY: Final = "intraday"
HORIZON_WEEK: Final = "week"
HORIZON_MONTH: Final = "month"
HORIZON_QUARTER: Final = "quarter"
HORIZON_YEAR_PLUS: Final = "year-plus"
HORIZONS: Final = (HORIZON_INTRADAY, HORIZON_WEEK, HORIZON_MONTH, HORIZON_QUARTER, HORIZON_YEAR_PLUS)
HORIZON_BOUNDS_MS: Final = (
    (HORIZON_INTRADAY, MS_PER_DAY),
    (HORIZON_WEEK, 7 * MS_PER_DAY),
    (HORIZON_MONTH, 31 * MS_PER_DAY),
    (HORIZON_QUARTER, 183 * MS_PER_DAY),
)

#: The builder labels of 7.14: a label a market may carry, not a facet it must. Weather series are
#: forecastable from public numerical models, which is decision D-R13's caveat on a weather claim.
LABEL_FORECASTABLE: Final = "forecastable_from_public_models"
BUILDER_LABELS: Final = (LABEL_FORECASTABLE,)

#: At most four subjects on one market (7.14), so ``tags`` cannot become the dump it replaced.
SUBJECTS_MAX: Final = 4
#: ``market.v2``'s caps on the two list fields (7.2).
TAGS_MAX: Final = 16
PROVIDER_LABELS_MAX: Final = 16

#: Which stage of 7.14 decided the subject facet: the sealed series map, the keyword rules, or nothing.
FACET_SOURCE_SERIES: Final = "series"
FACET_SOURCE_KEYWORDS: Final = "keywords"
FACET_SOURCE_OTHER: Final = "other"
FACET_SOURCES: Final = (FACET_SOURCE_SERIES, FACET_SOURCE_KEYWORDS, FACET_SOURCE_OTHER)

# --------------------------------------------------------------------------------------------------
# The coverage bar and its label (ruling R268, decision D-S14)
# --------------------------------------------------------------------------------------------------
#: Ninety percent **per venue** on the ``subject`` facet. Not ninety-five and not global: the prototype
#: measured 80.0 percent on Kalshi and 64.2 percent on Manifold, and Manifold's untagged tail is
#: genuinely unbounded, so one global bar would either be unreachable or would hide a real Kalshi
#: regression behind Manifold's noise.
TAXONOMY_COVERAGE_MIN_PERMILLE: Final = 900

#: A venue also needs ten usable cohorts to be labelled ``ok``: coverage with no cohort behind it is a
#: tagger that works and a dataset that still carries no comparison (decision D-S13).
TAXONOMY_MIN_USABLE_COHORTS: Final = 10

TAXONOMY_LABEL_OK: Final = "ok"
TAXONOMY_LABEL_WEAK: Final = "weak"

#: What a weak venue puts in ``LeaderboardRow.labels`` (12.10), exactly as ``news_links:weak`` is
#: carried for the linker (7.6).
TAXONOMY_WEAK_LABEL: Final = "taxonomy:weak"

#: How many taggings a build draws for a human to review (7.14, ruling R268). Fifty is what a reviewer
#: will actually read, which is the same number and the same reason as the linker audit's.
TAXONOMY_AUDIT_N: Final = 50

#: The audit file, beside ``linker.json`` in the **tracked** ``audits/<dataset_hash[:16]>/`` tree of
#: ruling R296. Outside every dataset hash, keyed by the hash it audits.
TAXONOMY_AUDIT_FILE: Final = "taxonomy.json"

#: The facets a reviewer records a verdict on, in reading order.
AUDIT_FACETS: Final = ("subject", "structure", "horizon")

_TAGS_CACHE: dict[str, TagLexicon] = {}
_SERIES_CACHE: dict[str, dict[str, SeriesFacets]] = {}


# --------------------------------------------------------------------------------------------------
# The vocabulary
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SubjectRule:
    """One subject of the vocabulary: its value, its keyword tokens and its builder labels.

    ``provider_labels`` is non-empty for ``platform-meta`` alone and is decision D-S14's reconciliation:
    7 of the 67 Manifold markets are self-referential by their question and 8 carry the provider's own
    non-predictive label, and **the two sets are not the same**, so trusting either alone leaves real
    non-forecasts inside forecast cohorts. The union of the two is one audited subject.
    """

    value: str
    keywords: frozenset[str] = frozenset()
    provider_labels: frozenset[str] = frozenset()
    builder_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StructureRule:
    """One structure of the vocabulary and the ordered regular expressions that decide it."""

    value: str
    patterns: tuple[re.Pattern[str], ...] = ()


@dataclass(frozen=True, slots=True)
class TagLexicon:
    """``tags.v1.json`` read into memory (7.14).

    ``subjects`` and ``structures`` are **ordered**, and the order is the file's: it is the tagger's
    precedence order for subjects and the first-match order for structures. Ruling R301 makes that order
    part of the version, so a reorder is a new file and a new dataset hash.
    """

    version: str
    subjects: tuple[SubjectRule, ...]
    structures: tuple[StructureRule, ...]
    horizons: tuple[str, ...]
    builder: tuple[str, ...]
    sha256: str = ""

    @property
    def subject_values(self) -> tuple[str, ...]:
        return tuple(rule.value for rule in self.subjects)

    @property
    def structure_values(self) -> tuple[str, ...]:
        return tuple(rule.value for rule in self.structures)

    @property
    def values(self) -> frozenset[str]:
        """Every value a ``tags`` list may hold: the three facets plus the builder labels (7.2, 7.14)."""
        return frozenset(
            {*self.subject_values, *self.structure_values, *self.horizons, *self.builder, VALUE_OTHER}
        )

    def subject_rule(self, value: str) -> SubjectRule | None:
        for rule in self.subjects:
            if rule.value == value:
                return rule
        return None

    def is_known(self, value: str) -> bool:
        return value in self.values


@dataclass(frozen=True, slots=True)
class SeriesFacets:
    """One row of ``kalshi_series_facets.v1.json``: what a series ticker fixes about its markets.

    ``structure`` is ``None`` on most rows on purpose. The structure facet is a statement about the
    *question's* shape, so it is read off the question wherever the question says it; a series may
    override it only where the ticker itself is the shape (a combination shard, a top-of-the-month
    multi-outcome event).
    """

    series: str
    subjects: tuple[str, ...] = ()
    structure: str | None = None


@dataclass(frozen=True, slots=True)
class Facets:
    """What the tagger returns for one market (7.14).

    ``source`` names the stage that decided the **subject** facet, which is the facet a cohort is keyed
    on and the one the coverage bar is measured on: ``series`` when the sealed map answered, ``keywords``
    when the vocabulary's rules did, ``other`` when nothing did. ``horizon`` is always derived, so it has
    no source of its own.
    """

    subject: tuple[str, ...]
    structure: str
    horizon: str
    labels: tuple[str, ...] = ()
    source: str = FACET_SOURCE_OTHER

    def __post_init__(self) -> None:
        if not self.subject:
            raise SchemaError("a market carries at least one subject, which is other at worst")
        if len(self.subject) > SUBJECTS_MAX:
            raise SchemaError(
                "a market carries at most four subjects (7.14)", subject=list(self.subject)
            )
        if len(set(self.subject)) != len(self.subject):
            raise SchemaError("the subject facet is unique", subject=list(self.subject))
        if self.source not in FACET_SOURCES:
            raise SchemaError("a facet source is series, keywords or other", source=self.source)
        if self.horizon not in HORIZONS:
            raise SchemaError("the horizon facet is one of five derived values", horizon=self.horizon)
        for value in (*self.subject, self.structure):
            if RE_FACET_VALUE.fullmatch(value) is None:
                raise SchemaError("a facet value is a lowercase slug (18.7)", value=value)
        # A builder label is not a facet value and is held to ``market.v2``'s ``tags`` pattern instead
        # (7.2): ``forecastable_from_public_models`` carries underscores, which 18.7's facet-value regex
        # forbids on purpose, because a facet value also has to be a segment of a cohort id.
        for label in self.labels:
            if label not in BUILDER_LABELS:
                raise SchemaError("a builder label the vocabulary does not ship (7.14)", label=label)

    @property
    def primary_subject(self) -> str:
        """``subject[0]``: the cohort key of 18.5, and the reason the subject facet is ordered."""
        return self.subject[0]

    @property
    def tags(self) -> tuple[str, ...]:
        """``tags`` (7.2): the sorted unique union of the facet values and the builder labels.

        The field **stays**, so ``Memory.prior(tag=...)``, ``PerMarket.tags``, a claim's ``per_tag`` and
        every other consumer keep working; what changes is that every value now means something.
        """
        return tuple(sorted({*self.subject, self.structure, self.horizon, *self.labels}))

    def to_dict(self) -> dict[str, object]:
        return {
            "subject": list(self.subject),
            "structure": self.structure,
            "horizon": self.horizon,
            "labels": list(self.labels),
            "source": self.source,
        }


@runtime_checkable
class TaggableMarket(Protocol):
    """Every field the tagger may read, and therefore every field it can read (7.9, 7.14).

    This protocol is the leak argument made structural. A facet, a provider label and a cohort id are
    data about the *question* that exist before the market's first bar, which is why they may sit in a
    ``MarketView`` and in a rule's scope at every bar. Keeping the tagger's input to a protocol that
    declares seven such fields means the refusal is not a convention a later edit can forget:
    ``resolution``, ``resolved_at_ms``, ``final_price_bp``, ``quality`` and ``bars`` are not names this
    module can reach.

    ``pmx.types.Market`` satisfies it. ``provider_labels`` is read through :func:`provider_labels_of`
    rather than declared here, because the field is 18.8's deferral row for ``src/pmx/types.py``: until
    it lands, a market's raw provider strings are still in ``tags``, which is where the tagger reads them
    from and where ``apply_facets`` moves them out of.
    """

    @property
    def id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def provider_id(self) -> str: ...

    @property
    def question(self) -> str: ...

    @property
    def category(self) -> str: ...

    @property
    def tags(self) -> tuple[str, ...]: ...

    @property
    def created_at_ms(self) -> int: ...

    @property
    def close_at_ms(self) -> int: ...


# --------------------------------------------------------------------------------------------------
# Reading the two files
# --------------------------------------------------------------------------------------------------
def _read_json(path: Path) -> object:
    if not path.is_file():
        raise InvalidConfigError("a lexicon file the tagger needs is not there", path=str(path))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidConfigError("a lexicon file is not readable JSON", path=str(path)) from error


def lexicon_sha256(path: Path) -> str:
    """The sha256 of a lexicon file's bytes, which is what the manifest records (7.8).

    Bytes and not a re-serialisation of the parsed object: the manifest's job is to say which file was
    used, and two files that parse the same and differ by a space are two files.
    """
    return sha256_hex(path.read_bytes())


def _subject_rules(payload: Mapping[str, object]) -> tuple[SubjectRule, ...]:
    rules: list[SubjectRule] = []
    for value, block in payload.items():
        if RE_FACET_VALUE.fullmatch(value) is None:
            raise InvalidConfigError("a subject value is a lowercase slug", value=value)
        if not isinstance(block, Mapping):
            raise InvalidConfigError("a subject entry is an object", value=value)
        keywords = block.get("keywords", [])
        labels = block.get("builder_labels", [])
        provider_labels = block.get("provider_labels", [])
        if (
            not isinstance(keywords, list)
            or not isinstance(labels, list)
            or not isinstance(provider_labels, list)
        ):
            raise InvalidConfigError("a subject entry's lists are lists", value=value)
        rules.append(
            SubjectRule(
                value=value,
                keywords=frozenset(word for word in keywords if isinstance(word, str)),
                provider_labels=frozenset(
                    label for label in provider_labels if isinstance(label, str)
                ),
                builder_labels=tuple(label for label in labels if isinstance(label, str)),
            )
        )
    return tuple(rules)


def _structure_rules(payload: Mapping[str, object]) -> tuple[StructureRule, ...]:
    rules: list[StructureRule] = []
    for value, block in payload.items():
        if RE_FACET_VALUE.fullmatch(value) is None:
            raise InvalidConfigError("a structure value is a lowercase slug", value=value)
        if not isinstance(block, Mapping):
            raise InvalidConfigError("a structure entry is an object", value=value)
        patterns = block.get("patterns", [])
        if not isinstance(patterns, list):
            raise InvalidConfigError("a structure entry's patterns are a list", value=value)
        compiled: list[re.Pattern[str]] = []
        for pattern in patterns:
            if not isinstance(pattern, str):
                raise InvalidConfigError("a structure pattern is a string", value=value)
            try:
                compiled.append(re.compile(pattern))
            except re.error as error:
                raise InvalidConfigError(
                    "a structure pattern is not a regular expression", value=value, pattern=pattern
                ) from error
        rules.append(StructureRule(value=value, patterns=tuple(compiled)))
    return tuple(rules)


def load_tag_lexicon(directory: Path | None = None) -> TagLexicon:
    """``tags.v1.json`` (7.14), cached by directory.

    A missing or malformed file is an ``InvalidConfigError`` and **not** an empty vocabulary. The linker
    of 7.6 degrades to "no stop words" on a missing file because a worse link is still a link; a missing
    tag vocabulary would silently tag every market ``other``, produce a dataset with no cohort, and pass
    every schema on the way, which is a build that looks like a build and carries no comparison.
    """
    root = LEXICON_DIR if directory is None else directory
    key = str(root)
    cached = _TAGS_CACHE.get(key)
    if cached is not None:
        return cached
    path = root / TAGS_FILE
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        raise InvalidConfigError("tags.v1.json is not an object", path=str(path))
    version = payload.get("version")
    facets = payload.get("facets")
    if not isinstance(version, str) or not isinstance(facets, Mapping):
        raise InvalidConfigError("tags.v1.json carries a version and a facets object", path=str(path))
    if version != TAGS_VERSION:
        raise InvalidConfigError(
            "this build reads tags.v1 and a new vocabulary version is a new dataset (ruling R301)",
            version=version,
        )
    subjects = facets.get("subject")
    structures = facets.get("structure")
    horizons = facets.get("horizon")
    builder = facets.get("builder")
    if (
        not isinstance(subjects, Mapping)
        or not isinstance(structures, Mapping)
        or not isinstance(horizons, list)
        or not isinstance(builder, list)
    ):
        raise InvalidConfigError("tags.v1.json's four facet blocks are missing or malformed")
    if tuple(value for value in horizons if isinstance(value, str)) != HORIZONS:
        raise InvalidConfigError(
            "the horizon facet is derived and its five values are fixed (7.14)", horizon=horizons
        )
    unknown_labels = sorted(
        label for label in builder if isinstance(label, str) and label not in BUILDER_LABELS
    )
    if unknown_labels:
        raise InvalidConfigError("an unknown builder label", labels=unknown_labels)
    lexicon = TagLexicon(
        version=version,
        subjects=_subject_rules(subjects),
        structures=_structure_rules(structures),
        horizons=HORIZONS,
        builder=tuple(label for label in builder if isinstance(label, str)),
        sha256=lexicon_sha256(path),
    )
    if VALUE_OTHER not in lexicon.subject_values or VALUE_OTHER not in lexicon.structure_values:
        raise InvalidConfigError(
            "the subject and structure facets each carry the counted other fallback (7.14)"
        )
    for rule in lexicon.subjects:
        unknown = sorted(label for label in rule.builder_labels if label not in lexicon.builder)
        if unknown:
            raise InvalidConfigError(
                "a subject declares a builder label the vocabulary does not ship",
                subject=rule.value,
                labels=unknown,
            )
    _TAGS_CACHE[key] = lexicon
    return lexicon


def load_series_facets(directory: Path | None = None) -> Mapping[str, SeriesFacets]:
    """``kalshi_series_facets.v1.json`` (7.14), cached by directory.

    The map is keyed on the series ticker, upper case, which is ruling R170's key and what
    :func:`series_ticker_of` computes. It never supersedes D2's ``kalshi_series_subjects.v1.json``
    (ruling R295): that file holds Wikipedia article titles the linker compares against a news item's
    ``wiki_links``, this one holds ``tags.v1`` facet values that group markets for a cohort.
    """
    root = LEXICON_DIR if directory is None else directory
    key = str(root)
    cached = _SERIES_CACHE.get(key)
    if cached is not None:
        return cached
    path = root / SERIES_FACETS_FILE
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        raise InvalidConfigError("kalshi_series_facets.v1.json is not an object", path=str(path))
    rows = payload.get("series")
    if not isinstance(rows, Mapping):
        raise InvalidConfigError("kalshi_series_facets.v1.json carries a series object")
    mapping: dict[str, SeriesFacets] = {}
    for series, block in rows.items():
        if not isinstance(block, Mapping):
            raise InvalidConfigError("a series facets entry is an object", series=series)
        subjects = block.get("subjects", [])
        structure = block.get("structure")
        if not isinstance(subjects, list) or (structure is not None and not isinstance(structure, str)):
            raise InvalidConfigError("a series facets entry is malformed", series=series)
        mapping[series.upper()] = SeriesFacets(
            series=series.upper(),
            subjects=tuple(value for value in subjects if isinstance(value, str))[:SUBJECTS_MAX],
            structure=structure,
        )
    _SERIES_CACHE[key] = mapping
    return mapping


def check_series_facets(
    series_facets: Mapping[str, SeriesFacets], *, lexicon: TagLexicon
) -> None:
    """Every value the series map names is a value the vocabulary ships, or ``InvalidConfigError``.

    The two files are shipped together and edited by the same package, which is exactly why this check
    exists: a subject renamed in one file and not the other would tag a whole Kalshi series with a value
    ``tags`` refuses, and the failure would surface at seal time on 220 markets at once.
    """
    unknown: list[str] = []
    for row in series_facets.values():
        unknown.extend(
            f"{row.series}:{value}" for value in row.subjects if value not in lexicon.subject_values
        )
        if row.structure is not None and row.structure not in lexicon.structure_values:
            unknown.append(f"{row.series}:{row.structure}")
    if unknown:
        raise InvalidConfigError(
            "the series facets map names a value tags.v1.json does not ship", values=sorted(unknown)
        )


# --------------------------------------------------------------------------------------------------
# The tagger (7.14, ruling R267): series map, then keywords, then a counted other
# --------------------------------------------------------------------------------------------------
def series_ticker_of(market: TaggableMarket) -> str | None:
    """The Kalshi series ticker of a market: the part of its ``provider_id`` before the first dash.

    ``None`` for every other provider. Manifold has no series and its ids are opaque, which is why its
    markets are tagged from their question alone and why its coverage is the lower of the two.
    """
    if market.provider != "kalshi":
        return None
    ticker = market.provider_id.split("-", 1)[0].strip().upper()
    return ticker or None


def tokens_of(question: str, stopwords: frozenset[str]) -> frozenset[str]:
    """The lowercase alphabetic tokens of a question, the stop list of 7.6 applied (7.14)."""
    return frozenset(TOKEN_RE.findall(question.lower())) - stopwords


def provider_labels_of(market: TaggableMarket) -> tuple[str, ...]:
    """The market's raw provider strings, sorted, unique and capped at sixteen (7.2).

    Read from ``provider_labels`` when the market carries it and from ``tags`` when it does not, which is
    the pre-taxonomy shape: an importer writes the provider's own strings into ``tags``, and
    :func:`apply_facets` is what moves them across. Values are normalised to ``market.v2``'s pattern
    (lowercase, ``[a-z0-9_-]``, 32 characters) because a label that cannot be written to the file is a
    label that would fail the market's own schema at seal time.
    """
    raw = getattr(market, "provider_labels", None)
    values: Iterable[object] = raw if isinstance(raw, tuple | list) and raw else market.tags
    normalised: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        slug = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")[:32]
        if slug and RE_TAG_VALUE.fullmatch(slug) is not None:
            normalised.add(slug)
    return tuple(sorted(normalised))[:PROVIDER_LABELS_MAX]


def horizon_of(created_at_ms: int, close_at_ms: int) -> str:
    """The horizon facet, derived from the market's declared life and from nothing else (7.14).

    ``life_ms = close_at_ms - created_at_ms``: the venue's **published** close, public on every venue
    from listing, never ``resolved_at_ms``. That is the whole leak argument for this facet, and it is why
    a market that settles late still carries the horizon it was listed with. A non-positive life (a
    provider that published a close at or before its own creation) is ``intraday``, which is what it is.
    """
    life_ms = close_at_ms - created_at_ms
    for value, bound_ms in HORIZON_BOUNDS_MS:
        if life_ms < bound_ms:
            return value
    return HORIZON_YEAR_PLUS


def _structure_from_question(question: str, *, lexicon: TagLexicon) -> str:
    """The first of the vocabulary's ordered patterns that matches the question, else ``other`` (7.14)."""
    lowered = question.lower()
    for rule in lexicon.structures:
        for pattern in rule.patterns:
            if pattern.search(lowered) is not None:
                return rule.value
    return VALUE_OTHER


def _subjects_from_keywords(
    tokens: frozenset[str], labels: frozenset[str], *, lexicon: TagLexicon
) -> tuple[str, ...]:
    """Every subject whose keywords or provider labels the market matches, in vocabulary order (7.14).

    Vocabulary order **is** precedence order, so the first hit is the primary subject and the cohort key.
    ``platform-meta`` sits first in the file for that reason: a self-referential market is not a forecast
    of the world, so it must not land in a forecast cohort because it also mentions bitcoin.
    """
    hits = [
        rule.value
        for rule in lexicon.subjects
        if rule.value != VALUE_OTHER
        and (bool(rule.keywords & tokens) or bool(rule.provider_labels & labels))
    ]
    return tuple(hits[:SUBJECTS_MAX])


def tag_market(
    market: TaggableMarket,
    *,
    lexicon: TagLexicon,
    series_facets: Mapping[str, SeriesFacets],
) -> Facets:
    """The three facets of one market, in the order 7.14 states and no other.

    1. the **sealed provider mapping** ``kalshi_series_facets.v1.json``: a series ticker to its subjects
       and, where the ticker fixes it, its structure. What it declares wins outright (``source =
       "series"``);
    2. the **keyword rules** of the vocabulary over the question's tokens, with the ``platform-meta``
       reconciliation reading the provider's own labels beside them, and the structure decided by the
       first of the ordered patterns that matches (``source = "keywords"``);
    3. a counted ``other`` for a facet nothing decided (``source = "other"``), which the manifest reports
       per venue so the gap is visible rather than absorbed.

    ``horizon`` is always derived. No network, no wall clock, no randomness, and no field of 7.9 is
    reachable: :class:`TaggableMarket` declares what may be read.
    """
    stopwords = load_stopwords()
    tokens = tokens_of(market.question, stopwords)
    labels = frozenset(provider_labels_of(market))
    ticker = series_ticker_of(market)
    row = series_facets.get(ticker) if ticker is not None else None

    subjects: tuple[str, ...] = ()
    source = FACET_SOURCE_OTHER
    if row is not None and row.subjects:
        subjects = row.subjects
        source = FACET_SOURCE_SERIES
    # The platform-meta reconciliation runs even when the series map answered: a series is a Kalshi
    # concept and platform-meta is a Manifold one, so the two never collide in practice, and a rule that
    # can only be reached when the earlier stage failed is a rule nobody can reason about.
    keyword_subjects = _subjects_from_keywords(tokens, labels, lexicon=lexicon)
    if not subjects and keyword_subjects:
        subjects = keyword_subjects
        source = FACET_SOURCE_KEYWORDS
    elif subjects and SUBJECT_PLATFORM_META in keyword_subjects:
        subjects = (SUBJECT_PLATFORM_META,)
        source = FACET_SOURCE_KEYWORDS
    if not subjects:
        subjects = (VALUE_OTHER,)
        source = FACET_SOURCE_OTHER

    structure = row.structure if row is not None and row.structure is not None else None
    if structure is None:
        structure = _structure_from_question(market.question, lexicon=lexicon)

    builder_labels: set[str] = set()
    for value in subjects:
        rule = lexicon.subject_rule(value)
        if rule is not None:
            builder_labels.update(rule.builder_labels)

    return Facets(
        subject=subjects,
        structure=structure,
        horizon=horizon_of(market.created_at_ms, market.close_at_ms),
        labels=tuple(sorted(builder_labels)),
        source=source,
    )


def tags_of(facets: Facets) -> tuple[str, ...]:
    """``tags`` (7.2): the sorted unique union of the market's facet values and builder labels."""
    return facets.tags


def check_tags(values: Sequence[str], *, lexicon: TagLexicon) -> None:
    """Refuse a ``tags`` value outside the shipped vocabulary (7.2, 7.14, ``SchemaError``).

    This is the check that makes the field mean something. Without it ``tags`` would drift back into the
    dump it replaced one importer at a time, and the drift would be invisible: every one of those 201
    provider strings matched ``market.v2``'s pattern.
    """
    if len(values) > TAGS_MAX:
        raise SchemaError("a market carries at most sixteen tags (7.2)", n=len(values))
    if list(values) != sorted(set(values)):
        raise SchemaError("tags are sorted and unique (7.2)", tags=list(values))
    unknown = sorted(value for value in values if not lexicon.is_known(value))
    if unknown:
        raise SchemaError(
            "a tags value outside the controlled vocabulary of 7.14",
            unknown=unknown,
            version=lexicon.version,
        )


def apply_facets(
    payload: Mapping[str, object], facets: Facets, *, provider_labels: Sequence[str], lexicon: TagLexicon
) -> dict[str, object]:
    """A ``market.v2`` payload with the taxonomy applied: this is the builder's one call site (7.14).

    ``tags`` becomes the facet union, the raw provider strings move **verbatim** to ``provider_labels``,
    and the three facet fields are written beside them. The refusal of :func:`check_tags` runs here, so a
    vocabulary and a tagger that disagree cannot produce a market file.
    """
    tags = list(tags_of(facets))
    check_tags(tags, lexicon=lexicon)
    labels = sorted(set(provider_labels))[:PROVIDER_LABELS_MAX]
    unknown = sorted(label for label in labels if RE_TAG_VALUE.fullmatch(label) is None)
    if unknown:
        raise SchemaError("a provider label outside market.v2's pattern (7.2)", labels=unknown)
    return {
        **dict(payload),
        "tags": tags,
        "provider_labels": labels,
        "subject": list(facets.subject),
        "structure": facets.structure,
        "horizon": facets.horizon,
    }


def copy_lexicons(dataset_dir: Path, *, directory: Path | None = None) -> tuple[str, str]:
    """Copy the two lexicon files into ``<dataset>/taxonomy/`` and answer their two hashes (7.8).

    The copy is **byte for byte**, which is the point: the directory is inside the walk of 4.3, so the
    two files are covered by ``dataset_hash``, and a vocabulary edit moves the hash of every dataset
    rebuilt with it rather than silently re-cutting an existing dataset's cohorts. A re-copy over an
    existing directory writes the same bytes and therefore moves nothing.
    """
    root = LEXICON_DIR if directory is None else directory
    out = dataset_dir / TAXONOMY_DIR
    out.mkdir(parents=True, exist_ok=True)
    hashes: list[str] = []
    for name in (TAGS_FILE, SERIES_FACETS_FILE):
        source = root / name
        if not source.is_file():
            raise InvalidConfigError("a lexicon file the dataset must carry is not there", path=str(source))
        payload = source.read_bytes()
        (out / name).write_bytes(payload)
        hashes.append(sha256_hex(payload))
    return hashes[0], hashes[1]


# --------------------------------------------------------------------------------------------------
# The manifest block (7.8, 7.14, rulings R265, R267, R268)
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TaggedMarket:
    """One market as the taxonomy block sees it: which venue it is on and what it was tagged."""

    market_id: str
    provider: str
    facets: Facets


@dataclass(frozen=True, slots=True)
class VenueTaxonomy:
    """One venue's row of ``manifest.taxonomy.per_venue`` (7.8, ruling R268)."""

    provider: str
    n_markets: int
    subject_coverage_permille: int
    structure_coverage_permille: int
    n_distinct_subjects: int
    n_other_subject: int
    n_other_structure: int
    n_platform_meta: int
    n_cohorts: int
    n_cohorts_usable: int

    @property
    def label(self) -> str:
        """``ok`` or ``weak``, **for this venue only** (ruling R268).

        Two ways to be weak and they are different failures: subject coverage below ninety percent is a
        vocabulary that does not fit the venue, and fewer than ten usable cohorts is a venue that carries
        no comparison whatever the coverage says. Both put ``taxonomy:weak`` on every leaderboard row and
        every chart that groups by a facet or a cohort, and neither hides the other.
        """
        if self.subject_coverage_permille < TAXONOMY_COVERAGE_MIN_PERMILLE:
            return TAXONOMY_LABEL_WEAK
        if self.n_cohorts_usable < TAXONOMY_MIN_USABLE_COHORTS:
            return TAXONOMY_LABEL_WEAK
        return TAXONOMY_LABEL_OK

    @property
    def weak(self) -> bool:
        return self.label == TAXONOMY_LABEL_WEAK

    def to_dict(self) -> dict[str, object]:
        """The manifest row: ``dataset.v1.json``'s nine keys and no tenth."""
        return {
            "subject_coverage_permille": self.subject_coverage_permille,
            "structure_coverage_permille": self.structure_coverage_permille,
            "n_distinct_subjects": self.n_distinct_subjects,
            "n_other_subject": self.n_other_subject,
            "n_other_structure": self.n_other_structure,
            "n_platform_meta": self.n_platform_meta,
            "n_cohorts": self.n_cohorts,
            "n_cohorts_usable": self.n_cohorts_usable,
            "label": self.label,
        }


def venue_taxonomy(
    provider: str, rows: Sequence[TaggedMarket], cohorts: Sequence[Cohort]
) -> VenueTaxonomy:
    """One venue's coverage, counted over the markets of that venue and its cohorts alone.

    ``coverage`` is the share of markets carrying a value other than ``other`` on the facet, which counts
    a ``platform-meta`` market as covered: naming a non-forecast is a tagging success, and the markets
    are counted separately in ``n_platform_meta`` so a reader can subtract them.
    """
    mine = [row for row in rows if row.provider == provider]
    n = len(mine)
    with_subject = sum(1 for row in mine if row.facets.primary_subject != VALUE_OTHER)
    with_structure = sum(1 for row in mine if row.facets.structure != VALUE_OTHER)
    subjects = {
        value for row in mine for value in row.facets.subject if value != VALUE_OTHER
    }
    theirs = [cohort for cohort in cohorts if cohort.provider == provider]
    return VenueTaxonomy(
        provider=provider,
        n_markets=n,
        subject_coverage_permille=round_half_up(1_000 * with_subject, n) if n else 0,
        structure_coverage_permille=round_half_up(1_000 * with_structure, n) if n else 0,
        n_distinct_subjects=len(subjects),
        n_other_subject=n - with_subject,
        n_other_structure=n - with_structure,
        n_platform_meta=sum(1 for row in mine if SUBJECT_PLATFORM_META in row.facets.subject),
        n_cohorts=len(theirs),
        n_cohorts_usable=sum(1 for cohort in theirs if cohort.n_train >= COHORT_MIN_TRAIN),
    )


def taxonomy_block(
    rows: Sequence[TaggedMarket],
    cohorts: Sequence[Cohort],
    *,
    lexicon: TagLexicon,
    lexicon_hash: str,
    series_facets_hash: str,
    audit: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """``manifest.taxonomy`` (7.8): the version, the two file hashes, the per-venue rows and the audit.

    The two hashes are the files copied into ``taxonomy/`` and therefore the ones inside
    ``dataset_hash``; the version is the one every ``per_cohort`` row of a claim copies as
    ``lexicon_version`` (ruling R301), so two claims cut under two vocabularies are comparable by a
    reader and not only by a machine.
    """
    providers = sorted({row.provider for row in rows})
    return {
        "version": lexicon.version,
        "lexicon_sha256": lexicon_hash,
        "series_facets_sha256": series_facets_hash,
        "per_venue": {
            provider: venue_taxonomy(provider, rows, cohorts).to_dict() for provider in providers
        },
        "cohort_size_histogram": cohort_size_histogram(cohorts),
        "audit": dict(audit) if audit is not None else None,
    }


def weak_venues(block: Mapping[str, object]) -> tuple[str, ...]:
    """The venues a manifest's taxonomy block labels ``weak``, read back off the block (12.10).

    A leaderboard row reads the label rather than recomputing it, for the reason ruling R301 gives about
    the lexicon version: the number exists once, in the manifest, and a second computation of it is a
    second thing that can disagree.
    """
    per_venue = block.get("per_venue")
    if not isinstance(per_venue, Mapping):
        return ()
    weak: list[str] = []
    for provider, row in per_venue.items():
        if isinstance(row, Mapping) and row.get("label") == TAXONOMY_LABEL_WEAK:
            weak.append(str(provider))
    return tuple(sorted(weak))


# --------------------------------------------------------------------------------------------------
# The fifty-tagging audit (7.14, rulings R268 and R296): tracked, keyed by the hash it audits
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TaxonomyVerdict:
    """One reviewed tagging: the market, what the tagger said, and the human's verdict per facet.

    ``verdicts`` is empty on a fresh file, which is what makes ``precision_permille`` read ``0``: a build
    whose taggings nobody has looked at is not a build whose taggings are good.
    """

    market_id: str
    question: str
    subject: tuple[str, ...]
    structure: str
    horizon: str
    source: str
    verdicts: Mapping[str, str | None] = field(default_factory=dict)
    reviewer: str = ""

    def __post_init__(self) -> None:
        unknown = sorted(facet for facet in self.verdicts if facet not in AUDIT_FACETS)
        if unknown:
            raise SchemaError("a taxonomy verdict names a facet that is not audited", facets=unknown)
        bad = sorted(
            f"{facet}:{verdict}"
            for facet, verdict in self.verdicts.items()
            if verdict is not None and verdict not in AUDIT_VERDICTS
        )
        if bad:
            raise SchemaError("a taxonomy verdict is correct, wrong or unsure", verdicts=bad)

    @property
    def n_correct(self) -> int:
        return sum(1 for verdict in self.verdicts.values() if verdict == "correct")

    @property
    def n_wrong(self) -> int:
        return sum(1 for verdict in self.verdicts.values() if verdict == "wrong")

    def to_dict(self) -> dict[str, object]:
        return {
            "market_id": self.market_id,
            "question": self.question,
            "subject": list(self.subject),
            "structure": self.structure,
            "horizon": self.horizon,
            "source": self.source,
            "verdicts": {facet: self.verdicts.get(facet) for facet in AUDIT_FACETS},
            "reviewer": self.reviewer,
        }


@dataclass(frozen=True, slots=True)
class TaxonomyAudit:
    """``audits/<dataset_hash[:16]>/taxonomy.json`` (7.14, rulings R268 and R296).

    Fifty taggings drawn with ``sample_without_replacement`` from the ``dataset.subsample`` substream,
    deterministic in the dataset and in nothing else: the same dataset always offers the same fifty for
    review, so an interrupted reviewer comes back to the same file and a second reviewer audits the same
    sample rather than a fresh one that could be shopped for.
    """

    dataset_hash: str
    sample_seed: int
    n: int
    taggings: tuple[TaxonomyVerdict, ...]

    @property
    def n_correct(self) -> int:
        return sum(row.n_correct for row in self.taggings)

    @property
    def n_wrong(self) -> int:
        return sum(row.n_wrong for row in self.taggings)

    @property
    def n_reviewed(self) -> int:
        return sum(1 for row in self.taggings if row.verdicts and any(row.verdicts.values()))

    @property
    def precision_permille(self) -> int:
        """``round_half_up(1000 * n_correct, n_correct + n_wrong)``, and ``0`` on an empty denominator.

        An ``unsure`` counts in neither half, exactly as it does for the linker audit: a reviewer who
        cannot tell is evidence about the reviewer and not about the tag.
        """
        denominator = self.n_correct + self.n_wrong
        if denominator == 0:
            return 0
        return round_half_up(1_000 * self.n_correct, denominator)

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_hash": self.dataset_hash,
            "sample_seed": self.sample_seed,
            "n": self.n,
            "taggings": [row.to_dict() for row in self.taggings],
            "precision_permille": self.precision_permille,
        }

    def manifest_block(self, path: str) -> dict[str, object]:
        """``manifest.taxonomy.audit {path, n, precision_permille}`` (7.8, ruling R268)."""
        return {"path": path, "n": self.n, "precision_permille": self.precision_permille}


def taxonomy_audit_path(root: Path, dataset_hash: str) -> Path:
    """``<root>/audits/<dataset_hash[:16]>/taxonomy.json`` (7.1, ruling R296)."""
    return audit_dir_for(root, dataset_hash) / TAXONOMY_AUDIT_FILE


def taxonomy_audit_manifest_path(dataset_hash: str) -> str:
    """The audit path as the manifest spells it, which ``dataset.v1.json``'s pattern pins."""
    if len(dataset_hash) < AUDIT_HASH_PREFIX:
        raise SchemaError("a dataset hash is sixty-four hex characters", dataset_hash=dataset_hash)
    return f"{AUDITS_DIR}/{dataset_hash[:AUDIT_HASH_PREFIX]}/{TAXONOMY_AUDIT_FILE}"


def sample_taxonomy_audit(
    rows: Sequence[TaggedMarket],
    questions: Mapping[str, str],
    *,
    dataset_hash: str,
    sample_seed: int,
    n: int = TAXONOMY_AUDIT_N,
) -> TaxonomyAudit:
    """Draw ``n`` taggings for review from the ``dataset.subsample`` substream (7.14, ruling R268).

    The population is every tagged market of the dataset, ``other`` taggings included: a facet nothing
    decided is exactly what a reviewer needs to see, and a sample drawn only from the confident taggings
    would measure the tagger's precision on the markets it already got right.
    """
    if n < 0:
        raise SchemaError("an audit draws a non-negative number of taggings", n=n)
    ordered = sorted(rows, key=lambda row: row.market_id)
    rng = RngTree(sample_seed).substream(AUDIT_SUBSTREAM)
    drawn = set(
        sample_without_replacement(rng, [row.market_id for row in ordered], min(n, len(ordered)))
    )
    taggings = tuple(
        TaxonomyVerdict(
            market_id=row.market_id,
            question=questions.get(row.market_id, ""),
            subject=row.facets.subject,
            structure=row.facets.structure,
            horizon=row.facets.horizon,
            source=row.facets.source,
            verdicts=dict.fromkeys(AUDIT_FACETS, None),
        )
        for row in ordered
        if row.market_id in drawn
    )
    return TaxonomyAudit(
        dataset_hash=dataset_hash, sample_seed=sample_seed, n=len(taggings), taggings=taggings
    )


def taxonomy_audit_from_dict(payload: object) -> TaxonomyAudit:
    """Read an audit file back, verdicts included, so the precision can be recomputed over them."""
    if not isinstance(payload, Mapping):
        raise SchemaError("a taxonomy audit file is not an object")
    dataset_hash = payload.get("dataset_hash")
    sample_seed = payload.get("sample_seed")
    n = payload.get("n")
    rows = payload.get("taggings")
    if (
        not isinstance(dataset_hash, str)
        or isinstance(sample_seed, bool)
        or not isinstance(sample_seed, int)
        or isinstance(n, bool)
        or not isinstance(n, int)
        or not isinstance(rows, list)
    ):
        raise SchemaError("a taxonomy audit file is malformed")
    taggings: list[TaxonomyVerdict] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise SchemaError("a taxonomy audit tagging is not an object")
        market_id = row.get("market_id")
        structure = row.get("structure")
        horizon = row.get("horizon")
        source = row.get("source")
        subject = row.get("subject")
        verdicts = row.get("verdicts", {})
        if (
            not isinstance(market_id, str)
            or not isinstance(structure, str)
            or not isinstance(horizon, str)
            or not isinstance(source, str)
            or not isinstance(subject, list)
            or not isinstance(verdicts, Mapping)
        ):
            raise SchemaError("a taxonomy audit tagging is malformed", market_id=market_id)
        question = row.get("question")
        reviewer = row.get("reviewer")
        taggings.append(
            TaxonomyVerdict(
                market_id=market_id,
                question=question if isinstance(question, str) else "",
                subject=tuple(value for value in subject if isinstance(value, str)),
                structure=structure,
                horizon=horizon,
                source=source,
                verdicts={
                    facet: value
                    for facet, value in verdicts.items()
                    if isinstance(facet, str) and (value is None or isinstance(value, str))
                },
                reviewer=reviewer if isinstance(reviewer, str) else "",
            )
        )
    return TaxonomyAudit(
        dataset_hash=dataset_hash,
        sample_seed=sample_seed,
        n=n,
        taggings=tuple(taggings),
    )
