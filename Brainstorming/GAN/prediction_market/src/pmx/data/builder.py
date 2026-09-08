"""The dataset builder: the twelve-month window, the quality filters, the hardness tags, the chronological
split and the manifest (CONTRACTS_V2 sections 7.4 to 7.8).

Why this module exists at all, and why it is the only writer: an importer that filtered and wrote its own
files would make a dataset a function of the order the providers were fetched in, and the count of what was
dropped would live nowhere. Section 7.12 therefore has every importer and fetcher return objects in memory,
and this module alone decides what enters a dataset, tags it, splits it, hashes it and writes it. What is
in a dataset and why is then one manifest, and the same inputs always produce the same bytes.

Two shapes of one build exist on purpose. ``build_dataset`` takes the ``Market`` and ``NewsItem`` objects
the importers return, which is the composition path of section 7.12. ``build_dataset_from_payloads`` takes
the same objects already rendered as JSON documents, which is what the CLI holds after reading a staged
import back off disk: re-parsing them into models only to render them again would buy nothing, and the
schema validation of ``pmx.data.schema`` runs on the payload either way. Everything downstream of that
boundary works on payloads, so there is exactly one place where a field name is spelled.

Bytes, hashes, seal and verify belong to D1 (``pmx.data.loader``) and are used here rather than reproduced:
a builder with its own writer would be a second definition of "what a dataset file is", and the first
divergence would show up as a hash that only one of the two could recompute.

Nothing here reads a clock (the freeze date is an argument and ``fetched_at_ms`` arrives on the items from
the fetcher that recorded it) and nothing here draws a random number (every selection is by canonical
order), so a build is reproducible and its hash is evidence.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pmx import CONTRACT_VERSION, DATASET_SCHEMA
from pmx import __version__ as PMX_VERSION
from pmx.data.loader import (
    dataset_files,
    dataset_hash_of,
    write_canonical_json,
    write_canonical_jsonl,
    write_manifest,
)
from pmx.data.news.linker import LinkIndex, load_stopwords, market_terms_of, tokens_of
from pmx.data.resample import median_daily_volume_milli_of
from pmx.data.schema import validate_against_schema
from pmx.errors import InvalidConfigError, LeakError, SchemaError
from pmx.rng import SEED_SPACE, RngTree, derive_seed, sample_without_replacement
from pmx.types import (
    LINK_THRESHOLD_PERMILLE,
    MS_PER_DAY,
    RE_DATASET_NAME,
    REMOVED_FILTER_KEYS,
    RNG_ALGORITHM_VERSION,
    TAPE_KIND_BARS_ONLY,
    TAPE_KIND_PRINTS,
    BuildConfig,
    BuiltBy,
    DatasetCounts,
    DatasetFile,
    DatasetFilters,
    DatasetManifest,
    DatasetNews,
    DatasetSplit,
    DatasetWindow,
    Market,
    NewsItem,
    NewsSourceCount,
    day_key,
    day_start_ms,
    hardness_tags_from_closes,
    month_edges_for,
)

__all__ = [
    "BACKGROUND_SOURCE",
    "ILLIQUID_DECILE_MIN_SLICE",
    "MULTI_OUTCOME_TAGS",
    "SAMPLE_SUBSTREAM",
    "SELF_RESOLVED_SOURCE",
    "SELF_RESOLVED_TAG",
    "BuildResult",
    "MarketFacts",
    "as_plain_dict",
    "build_config_from_manifest",
    "build_dataset",
    "build_dataset_from_payloads",
    "hardness_tags_for",
    "illiquid_boundaries",
    "link_news_payloads",
    "make_split",
    "market_facts",
    "month_index_of",
    "month_quotas",
    "news_floor_ms",
    "removal_reason",
    "sample_seed_for",
    "stratified_cap",
    "window_bounds",
]

#: The twelve month buckets of a window (CONTRACTS_V2 7.7: thirteen edges, twelve months). The cap is
#: stratified over them, and the manifest reports the pre-cap count of each.
MONTHS_PER_WINDOW = 12

#: The registered substream the per-provider cap draws from (CONTRACTS_V2 6.3). It is the only draw in a
#: build, and it is seeded from the dataset name alone, so the same name over the same staged markets
#: always samples the same dataset.
SAMPLE_SUBSTREAM = "dataset.subsample"

#: The per-market background archive of ``wiki_asof/``. It is deliberately not one of the digest sources a
#: build selects with ``BuildConfig.news_sources``: those defaults would silently drop the whole archive,
#: and a snapshot is written wherever it is handed to the builder (sections 7.1 and 7.3).
BACKGROUND_SOURCE = "wikipedia_asof"

#: The order the filters are *evaluated* in, which is what decides the bucket a market that fails several
#: of them lands in. The structural rules come first (a leg that is not a clean binary market is not a
#: market), then the leak rule, then the window, then the provider exclusions, then the quality bars. A
#: market that resolved after the freeze must read as ``no_leak`` and never as ``window``, because the two
#: mean different things to whoever reads the manifest.
FILTER_ORDER = (
    "resolution",
    "binary",
    "no_leak",
    "window",
    "opened_early",
    "self_resolved",
    "kalshi_shards",
    "min_trades",
    "min_life",
    "density",
)

#: Tags that name a leg which is not a single YES/NO market. A ``Market`` carries no outcome-type field,
#: so this is the only signal the ``binary`` filter of section 7.4 can read. The three are provider
#: outcome-type slugs and nothing else: a shorter word such as ``poll`` or ``multi`` would collide with a
#: Manifold group slug, which arrives in the same ``tags`` list, and would drop a legitimate binary market.
MULTI_OUTCOME_TAGS = ("free_response", "multi_outcome", "multiple_choice")

#: ``resolution_source`` of a market its own creator resolved. D3 records the fact here rather than
#: refusing the market, because on Manifold creator resolution is the normal case and refusing it at import
#: would return an empty provider; the decision and the count belong to this filter (section 7.4).
SELF_RESOLVED_SOURCE = "creator"

#: The same fact as a tag, for an importer that has no better channel. Read beside the marker above.
SELF_RESOLVED_TAG = "self_resolved"

#: Kalshi's auto-generated multi-leg shards resolve in minutes and carry no forecasting content. The prefix
#: is the contract's; the series list is data inside D2's importer and arrives as an argument.
KALSHI_SHARD_PREFIX = "KXMVE"

#: The category a market lands on when nothing named a better one (section 2's ``other``). It is
#: repeated here rather than imported from an importer, for the same reason the shard prefix is: the
#: builder never imports a provider's module.
CATEGORY_FALLBACK = "other"

#: A provider slice smaller than this has no tenth percentile worth the name, so nothing in it is tagged
#: ``illiquid`` and the manifest's note says the boundary was not computed.
ILLIQUID_DECILE_MIN_SLICE = 10

#: ``dataset.v1.json`` caps ``notes`` here.
NOTES_MAX = 4_000

_UPSET_WINDOW_MS = 30 * MS_PER_DAY


# --------------------------------------------------------------------------------------------------
# Typed reads of a JSON payload. The schema validates the whole document; these give the builder a typed
# view of the fields it reasons about, and a named error instead of a TypeError deep inside a filter.
# --------------------------------------------------------------------------------------------------
def _field(payload: Mapping[str, object], key: str) -> object:
    if key not in payload:
        raise SchemaError("a payload is missing a field the builder reads", field=key)
    return payload[key]


def _int_field(payload: Mapping[str, object], key: str) -> int:
    value = _field(payload, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError("a payload field is not an integer", field=key, kind=type(value).__name__)
    return value


def _opt_int_field(payload: Mapping[str, object], key: str) -> int | None:
    value = _field(payload, key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError("a payload field is not an integer or null", field=key, kind=type(value).__name__)
    return value


def _str_field(payload: Mapping[str, object], key: str) -> str:
    value = _field(payload, key)
    if not isinstance(value, str):
        raise SchemaError("a payload field is not a string", field=key, kind=type(value).__name__)
    return value


def _opt_str_field(payload: Mapping[str, object], key: str) -> str | None:
    value = _field(payload, key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SchemaError("a payload field is not a string or null", field=key, kind=type(value).__name__)
    return value


def _str_tuple_field(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = _field(payload, key)
    if not isinstance(value, list | tuple) or any(not isinstance(item, str) for item in value):
        raise SchemaError("a payload field is not a list of strings", field=key)
    return tuple(item for item in value if isinstance(item, str))


def _int_tuple_field(payload: Mapping[str, object], key: str) -> tuple[int, ...]:
    value = _field(payload, key)
    if not isinstance(value, list | tuple):
        raise SchemaError("a payload field is not a list of integers", field=key)
    out: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise SchemaError("a payload field is not a list of integers", field=key)
        out.append(item)
    return tuple(out)


def _object_field(payload: Mapping[str, object], key: str) -> dict[str, object]:
    value = _field(payload, key)
    if not isinstance(value, Mapping):
        raise SchemaError("a payload field is not an object", field=key, kind=type(value).__name__)
    return {str(name): item for name, item in value.items()}


def _object_list_field(payload: Mapping[str, object], key: str) -> tuple[Mapping[str, object], ...]:
    value = _field(payload, key)
    if not isinstance(value, list | tuple):
        raise SchemaError("a payload field is not a list", field=key)
    rows: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise SchemaError("a payload field is not a list of objects", field=key)
        rows.append({str(name): inner for name, inner in item.items()})
    return tuple(rows)


def as_plain_dict(obj: object) -> dict[str, object]:
    """Render one of D1's models (or a payload that is already plain) as the JSON document it serialises to.

    ``Market``, ``NewsItem`` and every other structure of ``pmx.types`` carry ``to_dict()``, which is the
    one renderer; a ``Mapping`` passes through so the object path and the payload path of this module meet
    here and nowhere else.
    """
    if isinstance(obj, Mapping):
        return {str(key): value for key, value in obj.items()}
    renderer = getattr(obj, "to_dict", None)
    if callable(renderer):
        rendered = renderer()
        if isinstance(rendered, Mapping):
            return {str(key): value for key, value in rendered.items()}
    raise SchemaError("cannot render this object as a JSON document", kind=type(obj).__name__)


def build_config_from_manifest(manifest: DatasetManifest, *, freeze_date: str | None = None) -> BuildConfig:
    """Rebuild the ``BuildConfig`` of an existing dataset, optionally sliding the freeze forward.

    This is what ``pmx data refresh`` runs on: the new dataset must differ from the old one in its window
    and in nothing else, and reading the knobs back out of the manifest is the only way to promise that.
    """
    config = dict(manifest.filters.config)
    limit = _int_field(config, "limit_per_provider")
    return BuildConfig(
        freeze_date=freeze_date if freeze_date is not None else _str_field(config, "freeze_date"),
        providers=_str_tuple_field(config, "providers"),
        interval_min=_int_field(config, "interval_min"),
        window_days=_int_field(config, "window_days"),
        opened_early_days=_int_field(config, "opened_early_days"),
        min_trades=_int_field(config, "min_trades"),
        min_unique_bettors=_int_field(config, "min_unique_bettors"),
        min_life_days=_int_field(config, "min_life_days"),
        # Absent from a manifest written before the bars-only branch of ``min_trades`` existed, so the
        # default of ``BuildConfig`` fills in rather than the refresh failing on an older dataset.
        min_traded_bars=(
            _int_field(config, "min_traded_bars")
            if "min_traded_bars" in config
            else BuildConfig(freeze_date="1970-01-01", providers=("demo",)).min_traded_bars
        ),
        min_traded_bars_per_day_permille=_int_field(config, "min_traded_bars_per_day_permille"),
        exclude_self_resolved=bool(_field(config, "exclude_self_resolved")),
        kalshi_series_allow_list=_str_tuple_field(config, "kalshi_series_allow_list"),
        exclude_kalshi_shards=bool(_field(config, "exclude_kalshi_shards")),
        safety_lag_ms=_int_field(config, "safety_lag_ms"),
        news_sources=_str_tuple_field(config, "news_sources"),
        limit_per_provider=limit if limit > 0 else None,
    )


# --------------------------------------------------------------------------------------------------
# The market, as the filters and the tags read it
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MarketFacts:
    """The numbers the filters, the tags and the split need, read once out of a market payload.

    ``traded_bars``, ``volume_milli_total`` and ``life_days`` are recomputed here from the tape rather than
    trusted from the importer's ``quality`` block, and the written market carries the recomputed values:
    the density filter is only as honest as the count it reads, and a provider's own volume field counts
    things (dollars, mana, contracts) that differ between venues.
    """

    id: str
    provider: str
    provider_id: str
    category: str
    source: str
    resolution_source: str
    tags: tuple[str, ...]
    created_at_ms: int
    close_at_ms: int
    resolved_at_ms: int
    resolution: int
    interval_min: int
    bar_times_ms: tuple[int, ...]
    closes_bp: tuple[int, ...]
    bar_volumes_milli: tuple[int, ...]
    bar_n_trades: tuple[int, ...]
    n_trades: int
    unique_bettors: int | None
    #: ``prints`` or ``bars_only`` (section 7.2). Read from the market file, defaulting to ``prints`` for
    #: a file written before the flag existed.
    tape_kind: str = TAPE_KIND_PRINTS

    @property
    def life_days(self) -> int:
        return max(0, self.resolved_at_ms - self.created_at_ms) // MS_PER_DAY

    @property
    def traded_bars(self) -> int:
        """Bars that saw activity: a print, or size on the bar itself.

        Both readings are needed and neither alone is honest. The migrated demo pack has prints whose
        size the source never gave (section 7.10 rule 5), so a bar with ``n_trades > 0`` and no volume
        traded. A settled Kalshi market has the opposite shape: the exchange publishes no settled print
        tape at all, so every bar carries ``n_trades == 0`` while the candlestick carries the volume and
        the open interest of the period. Counting prints alone made the density filter of 7.4 reject the
        whole of a provider whose tape is complete at bar resolution.
        """
        return sum(
            1
            for count, volume in zip(self.bar_n_trades, self.bar_volumes_milli, strict=True)
            if count > 0 or volume > 0
        )

    @property
    def volume_milli_total(self) -> int:
        return sum(self.bar_volumes_milli)

    @property
    def median_daily_volume_milli(self) -> int:
        return median_daily_volume_milli_of(list(zip(self.bar_times_ms, self.bar_volumes_milli, strict=True)))


def market_facts(payload: Mapping[str, object]) -> MarketFacts:
    """Read a ``market.v2`` payload into the facts the builder reasons about."""
    bars = _object_list_field(payload, "bars")
    quality = _object_field(payload, "quality")
    return MarketFacts(
        id=_str_field(payload, "id"),
        provider=_str_field(payload, "provider"),
        provider_id=_str_field(payload, "provider_id"),
        category=_str_field(payload, "category"),
        source=_str_field(payload, "source"),
        resolution_source=_str_field(payload, "resolution_source"),
        tags=_str_tuple_field(payload, "tags"),
        created_at_ms=_int_field(payload, "created_at_ms"),
        close_at_ms=_int_field(payload, "close_at_ms"),
        resolved_at_ms=_int_field(payload, "resolved_at_ms"),
        resolution=_int_field(payload, "resolution"),
        interval_min=_int_field(payload, "interval_min"),
        bar_times_ms=tuple(_int_field(bar, "t_ms") for bar in bars),
        closes_bp=tuple(_int_field(bar, "close_bp") for bar in bars),
        bar_volumes_milli=tuple(_int_field(bar, "volume_milli") for bar in bars),
        bar_n_trades=tuple(_int_field(bar, "n_trades") for bar in bars),
        n_trades=_int_field(quality, "n_trades"),
        unique_bettors=_opt_int_field(quality, "unique_bettors"),
        tape_kind=(
            _str_field(quality, "tape_kind") if "tape_kind" in quality else TAPE_KIND_PRINTS
        ),
    )


# --------------------------------------------------------------------------------------------------
# Window, filters, hardness tags, split
# --------------------------------------------------------------------------------------------------
def window_bounds(config: BuildConfig, facts: Sequence[MarketFacts]) -> tuple[int, int]:
    """The window on ``resolved_at_ms``: ``[freeze_ms - window_days, freeze_ms - 1 day)``.

    Section 7.1 exempts the migrated demo pack, whose markets resolved years before any freeze: a build
    whose only provider is ``demo`` takes its window from its own markets, exactly as the contract's
    manifest fixture does (start at the first creation day, end one millisecond after the last resolution).
    """
    freeze_ms = config.freeze_ms
    if tuple(config.providers) == ("demo",):
        if not facts:
            raise InvalidConfigError("a demo build needs at least one market")
        return (
            day_start_ms(min(item.created_at_ms for item in facts)),
            max(item.resolved_at_ms for item in facts) + 1,
        )
    return freeze_ms - config.window_days * MS_PER_DAY, freeze_ms - MS_PER_DAY


def removal_reason(
    facts: MarketFacts,
    config: BuildConfig,
    *,
    window_start_ms: int,
    window_end_ms: int,
    freeze_ms: int,
    excluded_series: frozenset[str] = frozenset(),
    window_checks: bool = True,
) -> str | None:
    """The first filter of ``FILTER_ORDER`` this market fails, or ``None`` when it is kept.

    One of the ten filters of section 7.4 reads a signal no field of ``market.v2`` carries: whether a leg is
    a single binary market (``binary``), which is read off ``tags`` because that is the only channel an
    importer has, and which is reported as a contract issue against section 7.2. ``self_resolved`` reads
    the ``resolution_source`` marker D3 declares, and the tag beside it for any importer that has none.
    """
    series = facts.provider_id.split("-", 1)[0]
    checks: dict[str, bool] = {
        "resolution": facts.resolution not in (0, 1),
        "binary": any(tag in MULTI_OUTCOME_TAGS for tag in facts.tags),
        "no_leak": window_checks and facts.resolved_at_ms >= freeze_ms,
        "window": window_checks and not (window_start_ms <= facts.resolved_at_ms < window_end_ms),
        "opened_early": (
            window_checks and facts.created_at_ms < window_start_ms - config.opened_early_days * MS_PER_DAY
        ),
        "self_resolved": config.exclude_self_resolved
        and (facts.resolution_source == SELF_RESOLVED_SOURCE or SELF_RESOLVED_TAG in facts.tags),
        "kalshi_shards": (
            config.exclude_kalshi_shards
            and facts.provider == "kalshi"
            and (facts.provider_id.startswith(KALSHI_SHARD_PREFIX) or series in excluded_series)
        ),
        # Three ways past this filter, one per shape of evidence a venue publishes. Prints and a trader
        # count are section 7.4's two; the third is the bars-only tape, whose ``n_trades`` is ``0``
        # because no settled print tape exists and not because nobody traded (section 7.2,
        # ``quality.tape_kind``). Without it the filter removed a whole provider whose bar tape carries
        # both volume and open interest, which is more size information than the survivors of the other
        # two branches often have.
        "min_trades": not (
            facts.n_trades >= config.min_trades
            or (facts.unique_bettors is not None and facts.unique_bettors >= config.min_unique_bettors)
            or (facts.tape_kind == TAPE_KIND_BARS_ONLY and facts.traded_bars >= config.min_traded_bars)
        ),
        "min_life": facts.resolved_at_ms - facts.created_at_ms < config.min_life_days * MS_PER_DAY,
        "density": facts.traded_bars * 1_000 < config.min_traded_bars_per_day_permille * facts.life_days,
    }
    for key in FILTER_ORDER:
        if checks[key]:
            return key
    return None


# --------------------------------------------------------------------------------------------------
# The cap, applied after the walk (section 7.4 ``limit_per_provider``)
# --------------------------------------------------------------------------------------------------
def month_index_of(resolved_at_ms: int, month_edges_ms: Sequence[int]) -> int:
    """The window month a resolution falls in, ``0`` to ``11``, clamped at both ends.

    The thirteen edges of section 7.7 are the same edges the fold split reads, so a stratified cap and
    the folds cut the window in the same places by construction. Clamping rather than raising is for the
    demo build, whose markets resolved years before any window and which skips the window filter.
    """
    for index in range(MONTHS_PER_WINDOW - 1, -1, -1):
        if resolved_at_ms >= month_edges_ms[index]:
            return index
    return 0


def month_quotas(counts: Sequence[int], limit: int) -> tuple[int, ...]:
    """How many markets each month keeps under ``limit``, as integers and in one deterministic order.

    Equal quota per month, the remainder to the months with the most candidates (ties to the earlier
    month), then any quota a thin month cannot fill is redistributed to the months that still have
    candidates, again largest first. The result sums to ``min(limit, sum(counts))``, so a cap never
    silently returns fewer markets than the window could offer, and it is a pure function of the counts:
    no clock, no draw, no dictionary order.
    """
    total = sum(counts)
    if limit <= 0 or total <= limit:
        return tuple(counts)
    months = len(counts)
    base, remainder = divmod(limit, months)
    by_size = sorted(range(months), key=lambda index: (-counts[index], index))
    targets = [base] * months
    for index in by_size[:remainder]:
        targets[index] += 1
    taken = [min(targets[index], counts[index]) for index in range(months)]
    deficit = limit - sum(taken)
    while deficit > 0:
        room = [index for index in by_size if taken[index] < counts[index]]
        if not room:
            break
        for index in room:
            taken[index] += 1
            deficit -= 1
            if deficit == 0:
                break
    return tuple(taken)


def sample_seed_for(name: str) -> int:
    """The root seed of a build's one draw, derived from the dataset name and nothing else.

    Not from a clock and not from the caller: two builds of the same name over the same staged markets
    must select the same markets, or a dataset hash stops being evidence of anything.
    """
    return derive_seed(0, f"dataset/{name}") % SEED_SPACE


def stratified_cap(
    facts: Sequence[MarketFacts],
    *,
    limit: int | None,
    month_edges_ms: Sequence[int],
    name: str,
) -> tuple[frozenset[str], dict[str, tuple[int, ...]]]:
    """``(kept ids, pre-cap counts per provider per month)``: the cap of section 7.4, after the filters.

    Why it is here and not in an importer: a cap applied while a provider is being walked truncates the
    **window**, and the first real build proved what that costs. Kalshi walks ascending by settlement and
    staged the first two days of the year; Manifold walks descending and staged the last thirteen days;
    every market that survived the filters landed in the sealed test fold, which section 12.7 forbids the
    optimizer to read, so there was nothing to train on. Applied here, after the whole window has been
    walked and filtered, the cap is a stratified sample: an equal quota per window month, the remainder
    to the months with the most candidates, and the members of each month drawn from the registered
    ``dataset.subsample`` substream seeded by the dataset name (section 6.3). Every fold is therefore
    populated whenever the window was, and the pre-cap counts go into the manifest so that a reviewer can
    see what the sample was drawn from.
    """
    by_provider: dict[str, list[list[str]]] = {}
    for item in facts:
        buckets = by_provider.setdefault(
            item.provider, [[] for _ in range(MONTHS_PER_WINDOW)]
        )
        buckets[month_index_of(item.resolved_at_ms, month_edges_ms)].append(item.id)
    precap = {
        provider: tuple(len(bucket) for bucket in buckets)
        for provider, buckets in sorted(by_provider.items())
    }
    if limit is None or limit <= 0:
        return frozenset(item.id for item in facts), precap
    rng = RngTree(sample_seed_for(name)).substream(SAMPLE_SUBSTREAM)
    kept: set[str] = set()
    for _provider, buckets in sorted(by_provider.items()):
        quotas = month_quotas([len(bucket) for bucket in buckets], limit)
        for bucket, quota in zip(buckets, quotas, strict=True):
            if quota >= len(bucket):
                kept.update(bucket)
                continue
            # Each month's candidates are sorted by id before the draw, so the sample is a function of
            # the dataset name and the market ids and not of the order the importers happened to return
            # them in. Two builds of the same staged markets are then the same dataset even if a
            # provider reorders its listing.
            kept.update(sample_without_replacement(rng, sorted(bucket), quota))
    return frozenset(kept), precap


def illiquid_boundaries(facts: Sequence[MarketFacts]) -> dict[str, int]:
    """The bottom-decile boundary of median daily volume, per provider slice, computed after the filters.

    The ``illiquid`` tag is relative by definition (section 7.5), so the boundary is data and is reported
    in the manifest's notes. A slice below ``ILLIQUID_DECILE_MIN_SLICE`` gets ``-1``, which no non-negative
    volume can reach, so nothing in it is tagged and the note says the boundary was not computed.
    """
    by_provider: dict[str, list[int]] = {}
    for item in facts:
        by_provider.setdefault(item.provider, []).append(item.median_daily_volume_milli)
    boundaries: dict[str, int] = {}
    for provider, medians in sorted(by_provider.items()):
        if len(medians) < ILLIQUID_DECILE_MIN_SLICE:
            boundaries[provider] = -1
            continue
        ordered = sorted(medians)
        boundaries[provider] = ordered[(len(ordered) - 1) // 10]
    return boundaries


def hardness_tags_for(facts: MarketFacts, *, illiquid_boundary_milli: int) -> tuple[str, ...]:
    """The stored, never-dropping, never-shown hardness tags of section 7.5, sorted.

    The arithmetic is :func:`pmx.types.hardness_tags_from_closes`, which ruling R89 made the one
    implementation of section 7.5: this wave shipped two (one here, one in ``pmx.types``) and they
    disagreed on the ``upset`` window, so one market could get two answers depending on who asked.

    What stays here is the only part that is not a property of the market: ``illiquid`` is relative to the
    dataset's provider slice, so the boundary that slice produced is compared here and passed in.
    """
    return hardness_tags_from_closes(
        bar_times_ms=facts.bar_times_ms,
        closes_bp=facts.closes_bp,
        resolution=facts.resolution,
        resolved_at_ms=facts.resolved_at_ms,
        illiquid=facts.median_daily_volume_milli <= illiquid_boundary_milli,
    )


def make_split(*, window_start_ms: int, fold_counts: Mapping[str, int]) -> DatasetSplit:
    """The thirteen month edges of section 7.7 and the three fold counts, cut at months 8 and 10."""
    edges = month_edges_for(window_start_ms)
    return DatasetSplit(
        month_edges_ms=edges,
        train_end_ms=edges[8],
        validation_end_ms=edges[10],
        n_train=fold_counts.get("train", 0),
        n_validation=fold_counts.get("validation", 0),
        n_sealed=fold_counts.get("sealed", 0),
    )


def _fold_of(resolved_at_ms: int, *, train_end_ms: int, validation_end_ms: int) -> str:
    if resolved_at_ms < train_end_ms:
        return "train"
    if resolved_at_ms < validation_end_ms:
        return "validation"
    return "sealed"


# --------------------------------------------------------------------------------------------------
# The build
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BuildResult:
    """What a build produced: for the CLI to print, and for a test to assert against."""

    path: Path
    manifest: DatasetManifest
    kept_ids: tuple[str, ...]
    removed: dict[str, int]
    folds: dict[str, str]
    hardness: dict[str, tuple[str, ...]]
    illiquid_boundaries: dict[str, int]
    window: tuple[int, int]
    n_news_items: int
    n_news_linked: int
    n_news_dropped: int
    n_bytes: int

    @property
    def dataset_hash(self) -> str:
        return self.manifest.dataset_hash


def _sorted_markets(payloads: Sequence[Mapping[str, object]]) -> tuple[Mapping[str, object], ...]:
    """Markets in the canonical order of section 3: ``(resolved_at_ms, id)`` ascending."""
    return tuple(sorted(payloads, key=lambda p: (_int_field(p, "resolved_at_ms"), _str_field(p, "id"))))


def _news_sort_key(payload: Mapping[str, object]) -> tuple[int, str]:
    return (_int_field(payload, "published_at_ms"), _str_field(payload, "news_id"))


def news_floor_ms(*, window_start_ms: int, opened_early_days: int) -> int:
    """The earliest publication a dataset's news archive keeps.

    The window filter admits a market that opened up to ``opened_early_days`` before the window
    (section 7.4), so the news of the time has to reach back exactly that far and no further. Nothing in
    section 7.3 bounds the archive below, and an unbounded one is not merely untidy: every item is visible
    at every bar once its lag has run, so a year-old headline left over from a previous window would sit
    in ``news_global`` for the whole run and crowd out the news that was actually current.
    """
    return window_start_ms - opened_early_days * MS_PER_DAY


def link_news_payloads(
    news_payloads: Sequence[Mapping[str, object]],
    market_payloads: Sequence[Mapping[str, object]],
    *,
    threshold_permille: int = LINK_THRESHOLD_PERMILLE,
) -> tuple[dict[str, object], ...]:
    """Copies of the news payloads with the linker of section 7.6 applied against the kept markets.

    This is the step that was missing: ``link_items`` existed, was tested, and nothing in the build path
    called it, so the only links a real dataset carried were the ones a Manifold comment states about its
    own market, and the 7 391 Wikipedia Current events items of the first real build linked to nothing at
    all. Per-market news is the input the news-reading families and the LLM forecaster were designed
    around, so an unlinked archive disables them however complete it is.

    A link an item already carries is kept and the higher score wins (ruling R95), the lists come out
    sorted by market id with their scores aligned, and the arithmetic is the linker's alone: this
    function only feeds it the payload fields and merges the answer back.
    """
    stopwords = load_stopwords()
    index = LinkIndex(
        [
            market_terms_of(
                market_id=_str_field(payload, "id"),
                question=_str_field(payload, "question"),
                tags=_str_tuple_field(payload, "tags"),
                wiki_subjects=_str_tuple_field(payload, "wiki_subjects"),
                stopwords=stopwords,
            )
            for payload in market_payloads
        ]
    )
    linked: list[dict[str, object]] = []
    for raw in news_payloads:
        payload = dict(raw)
        scores: dict[str, int] = dict(
            zip(
                _str_tuple_field(payload, "match_ids"),
                _int_tuple_field(payload, "match_scores_permille"),
                strict=True,
            )
        )
        for market_id, score in index.links_for(
            item_links=_str_tuple_field(payload, "wiki_links"),
            item_keywords=tokens_of(
                (_str_field(payload, "headline"), _str_field(payload, "text")), stopwords
            ),
            threshold_permille=threshold_permille,
        ):
            scores[market_id] = max(score, scores.get(market_id, 0))
        hits = sorted(scores.items())
        payload["match_ids"] = [market_id for market_id, _ in hits]
        payload["match_scores_permille"] = [score for _, score in hits]
        linked.append(payload)
    return tuple(linked)


def _prepare_news(
    payloads: Sequence[Mapping[str, object]],
    *,
    config: BuildConfig,
    kept_ids: frozenset[str],
    freeze_ms: int,
    floor_ms: int,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...], int]:
    """Validate, filter and re-link the news archive: the digest items, the background items, the dropped.

    Four rules bite here. An item published after the freeze is a leak and stops the build (section 5.6):
    it is not filtered, because nothing legitimate produces one. An item whose ``visible_from_ms`` is
    earlier than ``published_at_ms + safety_lag_ms`` is the same leak wearing the lag's clothes, and one
    that is later is a malformed item the loader would refuse. An item published before ``floor_ms``
    predates every market of the dataset and is dropped. And an item's ``match_ids`` are pruned to the
    markets that survived the filters, with their scores, so no dataset points at a market it does not
    contain; an item that ends up linked to nothing is still kept, because ``Dataset.news_global`` is a
    real reading of the news of the time.
    """
    digest: list[dict[str, object]] = []
    background: list[dict[str, object]] = []
    dropped = 0
    seen_ids: set[str] = set()
    for raw in payloads:
        validate_against_schema("news.v1.json", dict(raw), where="news item")
        payload = dict(raw)
        news_id = _str_field(payload, "news_id")
        if news_id in seen_ids:
            raise SchemaError("two news items share a news_id", news_id=news_id)
        seen_ids.add(news_id)
        source = _str_field(payload, "source")
        published_at_ms = _int_field(payload, "published_at_ms")
        visible_from_ms = _int_field(payload, "visible_from_ms")
        if published_at_ms > freeze_ms:
            raise LeakError(
                "a news item is published after the freeze",
                news_id=news_id,
                published_at_ms=published_at_ms,
                freeze_ms=freeze_ms,
            )
        expected_visible_ms = published_at_ms + config.safety_lag_ms
        if visible_from_ms < expected_visible_ms:
            raise LeakError(
                "a news item is visible before its safety lag has run",
                news_id=news_id,
                visible_from_ms=visible_from_ms,
                expected_visible_ms=expected_visible_ms,
            )
        if visible_from_ms != expected_visible_ms:
            raise SchemaError(
                "visible_from_ms is not published_at_ms plus the dataset's safety lag",
                news_id=news_id,
                visible_from_ms=visible_from_ms,
                expected_visible_ms=expected_visible_ms,
            )
        if published_at_ms < floor_ms:
            dropped += 1
            continue
        if source != BACKGROUND_SOURCE and source not in config.news_sources:
            dropped += 1
            continue
        match_ids = _str_tuple_field(payload, "match_ids")
        scores = _int_tuple_field(payload, "match_scores_permille")
        if len(match_ids) != len(scores):
            raise SchemaError("match_ids and match_scores_permille differ in length", news_id=news_id)
        pairs = [(mid, score) for mid, score in zip(match_ids, scores, strict=True) if mid in kept_ids]
        payload["match_ids"] = [mid for mid, _ in pairs]
        payload["match_scores_permille"] = [score for _, score in pairs]
        if source == BACKGROUND_SOURCE:
            if not pairs:
                dropped += 1
                continue
            background.append(payload)
        else:
            digest.append(payload)
    return (
        tuple(sorted(digest, key=_news_sort_key)),
        tuple(sorted(background, key=_news_sort_key)),
        dropped,
    )


def _news_sources(items: Sequence[Mapping[str, object]]) -> tuple[NewsSourceCount, ...]:
    """One ``manifest.news.sources`` row per source present, sorted by source name."""
    per_source: dict[str, list[int]] = {}
    for payload in items:
        per_source.setdefault(_str_field(payload, "source"), []).append(_int_field(payload, "fetched_at_ms"))
    return tuple(
        NewsSourceCount(
            source=source,
            n_items=len(stamps),
            fetched_at_ms_min=min(stamps),
            fetched_at_ms_max=max(stamps),
        )
        for source, stamps in sorted(per_source.items())
    )


def _counts(
    facts: Sequence[MarketFacts],
    hardness: Mapping[str, tuple[str, ...]],
    boundaries: Mapping[str, int],
    *,
    precap_per_provider_month: Mapping[str, tuple[int, ...]] = {},
    mapped_series: frozenset[str] = frozenset(),
) -> DatasetCounts:
    per_provider: dict[str, int] = {}
    per_category: dict[str, int] = {}
    per_tag: dict[str, int] = {}
    yes = 0
    bars_only = 0
    category_fallback = 0
    for item in facts:
        per_provider[item.provider] = per_provider.get(item.provider, 0) + 1
        per_category[item.category] = per_category.get(item.category, 0) + 1
        yes += 1 if item.resolution == 1 else 0
        bars_only += 1 if item.tape_kind == TAPE_KIND_BARS_ONLY else 0
        # A fallback is a market whose provider published no category and whose series the caller's
        # series-to-category map does not name. The map arrives as an argument for the reason the
        # excluded-series list does: the builder never imports a provider's importer.
        if (
            mapped_series
            and item.category == CATEGORY_FALLBACK
            and item.provider_id.split("-", 1)[0].upper() not in mapped_series
        ):
            category_fallback += 1
        for tag in hardness.get(item.id, ()):
            per_tag[tag] = per_tag.get(tag, 0) + 1
    return DatasetCounts(
        markets=len(facts),
        per_provider=dict(sorted(per_provider.items())),
        per_category=dict(sorted(per_category.items())),
        resolution_yes=yes,
        resolution_no=len(facts) - yes,
        hardness_tags=dict(sorted(per_tag.items())),
        n_bars_only=bars_only,
        n_category_fallback=category_fallback,
        precap_per_provider_month=dict(sorted(precap_per_provider_month.items())),
        # A negative boundary is the "slice too small for a tenth percentile" marker of
        # ``illiquid_boundaries``; it is not a boundary, so it is named in ``notes`` and not here.
        illiquid_boundary_milli={
            provider: value for provider, value in sorted(boundaries.items()) if value >= 0
        },
    )


def _boundary_note(boundaries: Mapping[str, int]) -> str:
    """The human sentence beside ``counts.illiquid_boundary_milli`` (ruling R98).

    The typed field carries the boundaries that exist; this names the provider slices that were too small
    for a tenth percentile, which the field cannot say because it only holds real boundaries.
    """
    if not boundaries:
        return ""
    parts = [
        f"{provider}={value} milli"
        if value >= 0
        else f"{provider}=not computed (slice under {ILLIQUID_DECILE_MIN_SLICE})"
        for provider, value in sorted(boundaries.items())
    ]
    return "illiquid decile boundary: " + ", ".join(parts)


def build_dataset_from_payloads(
    *,
    out_dir: Path,
    config: BuildConfig,
    market_payloads: Sequence[Mapping[str, object]],
    news_payloads: Sequence[Mapping[str, object]] = (),
    excluded_series: Sequence[str] = (),
    mapped_series: Sequence[str] = (),
    name: str | None = None,
    notes: str = "",
    overwrite: bool = False,
) -> BuildResult:
    """Filter, tag, split, write and hash a dataset directory from already rendered JSON documents.

    The order of operations is the order the contract's counts assume: validate, filter (each removed
    market counted once, by the first rule it failed), **then** cap per provider by the stratified sample
    of :func:`stratified_cap`, recompute the quality block from the tape, tag hardness relative to the
    surviving provider slice, link the news archive against the kept markets, split by ``resolved_at_ms``,
    write, digest. The cap comes after the filters and not before: capping first threw away markets the
    filters would have kept and left the folds unpopulated (see :func:`stratified_cap`).
    ``sealed`` stays ``false``: only ``pmx data seal`` sets it, after refusing every reconstructed market.

    ``mapped_series`` is the set of provider series a caller's series-to-category map names, and is used
    for one number: how many kept markets fell back to the ``other`` category (section 2). It arrives as
    an argument for the same reason ``excluded_series`` does.
    """
    dataset_name = name if name is not None else out_dir.name
    if RE_DATASET_NAME.fullmatch(dataset_name) is None:
        raise InvalidConfigError("a dataset name is not the lowercase slug of section 2", name=dataset_name)
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists() and not overwrite:
        raise InvalidConfigError(
            "a dataset already exists here and a dataset is never edited in place",
            path=str(manifest_path),
        )

    ordered = _sorted_markets(market_payloads)
    for payload in ordered:
        validate_against_schema("market.v2.json", dict(payload), where="market")

    seen_ids: set[str] = set()
    all_facts: list[MarketFacts] = []
    for payload in ordered:
        facts = market_facts(payload)
        if facts.id in seen_ids:
            raise InvalidConfigError("two markets share an id", market_id=facts.id)
        seen_ids.add(facts.id)
        if facts.interval_min != config.interval_min:
            raise InvalidConfigError(
                "a market is on another grid than the dataset (section 5.3: one grid per dataset)",
                market_id=facts.id,
                market_interval_min=facts.interval_min,
                dataset_interval_min=config.interval_min,
            )
        if facts.provider not in config.providers:
            raise InvalidConfigError(
                "a market's provider is not one this build asked for",
                market_id=facts.id,
                provider=facts.provider,
            )
        all_facts.append(facts)

    window_start_ms, window_end_ms = window_bounds(config, all_facts)
    freeze_ms = config.freeze_ms
    excluded = frozenset(excluded_series)
    removed = dict.fromkeys(REMOVED_FILTER_KEYS, 0)
    kept_payloads: list[Mapping[str, object]] = []
    kept_facts: list[MarketFacts] = []
    for payload, facts in zip(ordered, all_facts, strict=True):
        reason = removal_reason(
            facts,
            config,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            freeze_ms=freeze_ms,
            excluded_series=excluded,
            window_checks=tuple(config.providers) != ("demo",),
        )
        if reason is not None:
            removed[reason] += 1
            continue
        kept_payloads.append(payload)
        kept_facts.append(facts)

    # The cap of section 7.4, after the walk and after the filters (:func:`stratified_cap`).
    sampled_ids, precap = stratified_cap(
        kept_facts,
        limit=config.limit_per_provider,
        month_edges_ms=month_edges_for(window_start_ms),
        name=dataset_name,
    )
    if len(sampled_ids) < len(kept_facts):
        kept_pairs = [
            (payload, facts)
            for payload, facts in zip(kept_payloads, kept_facts, strict=True)
            if facts.id in sampled_ids
        ]
        kept_payloads = [payload for payload, _ in kept_pairs]
        kept_facts = [facts for _, facts in kept_pairs]

    boundaries = illiquid_boundaries(kept_facts)
    hardness = {
        facts.id: hardness_tags_for(facts, illiquid_boundary_milli=boundaries.get(facts.provider, -1))
        for facts in kept_facts
    }
    edges = month_edges_for(window_start_ms)
    folds = {
        facts.id: _fold_of(facts.resolved_at_ms, train_end_ms=edges[8], validation_end_ms=edges[10])
        for facts in kept_facts
    }
    fold_counts: dict[str, int] = {}
    for fold in folds.values():
        fold_counts[fold] = fold_counts.get(fold, 0) + 1
    split = make_split(window_start_ms=window_start_ms, fold_counts=fold_counts)
    if split.n_train + split.n_validation + split.n_sealed != len(kept_facts):
        raise InvalidConfigError(
            "the three folds do not partition the kept markets",
            n_kept=len(kept_facts),
            n_train=split.n_train,
            n_validation=split.n_validation,
            n_sealed=split.n_sealed,
        )

    # The linker of section 7.6, against the markets this dataset actually contains. Nothing in the
    # build path called it before, so a real dataset's only links were the ones a comment states.
    linked_news = link_news_payloads(news_payloads, kept_payloads)
    digest_news, background_news, dropped_news = _prepare_news(
        linked_news,
        config=config,
        kept_ids=frozenset(folds),
        freeze_ms=freeze_ms,
        floor_ms=news_floor_ms(
            window_start_ms=window_start_ms,
            opened_early_days=config.opened_early_days,
        ),
    )

    if overwrite:
        _clear(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_bytes = 0
    for payload, facts in zip(kept_payloads, kept_facts, strict=True):
        document = dict(payload)
        document["hardness_tags"] = list(hardness[facts.id])
        quality = _object_field(payload, "quality")
        quality["life_days"] = facts.life_days
        quality["traded_bars"] = facts.traded_bars
        quality["volume_milli_total"] = facts.volume_milli_total
        document["quality"] = quality
        validate_against_schema("market.v2.json", document, where="market")
        n_bytes += write_canonical_json(out_dir / "markets" / f"{facts.id}.json", document)

    by_day: dict[str, list[dict[str, object]]] = {}
    for payload in digest_news:
        by_day.setdefault(day_key(day_start_ms(_int_field(payload, "published_at_ms"))), []).append(payload)
    for key, items in sorted(by_day.items()):
        n_bytes += write_canonical_jsonl(out_dir / "news" / f"{key}.jsonl", items)

    for payload in background_news:
        market_id = _str_tuple_field(payload, "match_ids")[0]
        asof_day = _opt_str_field(payload, "asof_day")
        if asof_day is None:
            raise SchemaError("a background snapshot carries no asof_day", news_id=_str_field(payload, "news_id"))
        path = out_dir / "wiki_asof" / market_id / f"{asof_day.replace('-', '')}.json"
        n_bytes += write_canonical_json(path, payload)

    files: tuple[DatasetFile, ...] = dataset_files(out_dir)
    all_news = list(digest_news) + list(background_news)
    n_linked = sum(1 for item in all_news if _str_tuple_field(item, "match_ids"))
    note_parts = [part for part in (notes.strip(), _boundary_note(boundaries)) if part]
    manifest = DatasetManifest(
        schema_version=DATASET_SCHEMA,
        name=dataset_name,
        freeze_date=config.freeze_date,
        freeze_ms=freeze_ms,
        window=DatasetWindow(start_ms=window_start_ms, end_ms=window_end_ms),
        interval_min=config.interval_min,
        providers=tuple(config.providers),
        safety_lag_ms=config.safety_lag_ms,
        filters=DatasetFilters(config=config.to_dict(), removed=removed),
        counts=_counts(
            kept_facts,
            hardness,
            boundaries,
            precap_per_provider_month=precap,
            mapped_series=frozenset(series.upper() for series in mapped_series),
        ),
        news=DatasetNews(sources=_news_sources(all_news), n_items=len(all_news), n_linked=n_linked),
        split=split,
        files=files,
        dataset_hash=dataset_hash_of(files),
        built_by=BuiltBy(
            pmx_version=PMX_VERSION,
            contract_version=CONTRACT_VERSION,
            rng_algorithm_version=RNG_ALGORITHM_VERSION,
        ),
        sealed=False,
        notes="; ".join(note_parts)[:NOTES_MAX],
    )
    validate_against_schema("dataset.v1.json", manifest.to_dict(), where="dataset manifest")
    n_bytes += write_manifest(out_dir, manifest)

    return BuildResult(
        path=out_dir,
        manifest=manifest,
        kept_ids=tuple(facts.id for facts in kept_facts),
        removed=removed,
        folds=folds,
        hardness=hardness,
        illiquid_boundaries=boundaries,
        window=(window_start_ms, window_end_ms),
        n_news_items=len(all_news),
        n_news_linked=n_linked,
        n_news_dropped=dropped_news,
        n_bytes=n_bytes,
    )


def _clear(out_dir: Path) -> None:
    """Remove the three hashed directories of a dataset being rebuilt in place.

    Only ``markets/``, ``news/`` and ``wiki_asof/`` are touched: ``cache/`` is the raw provider answers a
    rebuild wants to keep, and ``contamination.json`` is per model and outside the hash (sections 7.1,
    11.5). A stale file left behind would enter the next hash and make the manifest a lie.
    """
    for name in ("markets", "news", "wiki_asof"):
        shutil.rmtree(out_dir / name, ignore_errors=True)


def build_dataset(
    *,
    out_dir: Path,
    config: BuildConfig,
    markets: Sequence[Market],
    news: Sequence[NewsItem] = (),
    excluded_series: Sequence[str] = (),
    mapped_series: Sequence[str] = (),
    name: str | None = None,
    notes: str = "",
    overwrite: bool = False,
) -> BuildResult:
    """``build_dataset_from_payloads`` over the objects the importers and fetchers of section 7.12 return."""
    return build_dataset_from_payloads(
        out_dir=out_dir,
        config=config,
        market_payloads=[as_plain_dict(market) for market in markets],
        news_payloads=[as_plain_dict(item) for item in news],
        excluded_series=excluded_series,
        mapped_series=mapped_series,
        name=name,
        notes=notes,
        overwrite=overwrite,
    )
