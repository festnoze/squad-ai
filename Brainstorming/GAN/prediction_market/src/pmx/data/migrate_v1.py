"""Turning the twelve v1 demo markets into a v2 dataset: ``data/demo_v1/``.

The demo pack is the only dataset committed to the repository and, until the first real build seals one,
the only tape the engine, the agents and the optimizer have to run against. That makes the identities of
CONTRACTS_V2 section 7.10 normative rather than decorative, and they are what this module holds:

1. the grid is daily and aligned (``interval_min == 1_440``, every ``bar.t_ms`` a multiple of a day);
2. bars are dense from ``bar_of(created_at_ms)`` to ``bar_of(resolved_at_ms)``, one per day, no gap and
   no duplicate;
3. ``first_price_bp`` and ``final_price_bp`` are the first and last v1 control points times 100, and a
   bar between two control points carries the previous one forward as
   ``open == high == low == close == vwap``;
4. ``source == "reconstructed"``, ``provider == "demo"``, ``id == f"demo-{v1_id}"``,
   ``currency == "usd"``, ``fee_schedule_id == "demo-zero"``, ``trades == []``, and ``wiki_subjects``
   from :data:`DEMO_WIKI_SUBJECTS` (ruling R97 amended the identity, which used to say ``[]`` while the
   contract's own fixture carried a real article title and ``test_contract_schemas.py`` asserted it was
   non-empty; a demo pack with no subjects is also invisible to the linker of section 7.6, which compares
   an item's ``wiki_links`` against exactly this field);
5. ``volume_milli == 0`` and ``n_trades == 0`` on every bar, because v1 has no volume. The pack is still
   tradable: section 8.6 step 1 exempts a ``reconstructed`` market from the volume rules rather than
   inventing a volume the source never had;
6. ``hardness_tags`` is computed by section 7.5 on the migrated bars, so Brexit carries ``upset``.

**Honesty, restated because it is easy to lose.** The events and the outcomes are real and verifiable;
the price paths are reconstructed from how each market actually behaved. That is why every market carries
``source: "reconstructed"``, why ``seal_dataset`` refuses the pack, and why no claim can ever be made
against it: a plausible path is a test vehicle, not evidence.

The day a control point falls on is the day it moves the price, and a day with several points takes the
**previous** close as its open, the last point as its close, and the extremes over both: that is what
makes the Brexit night (22 at 20:00, 30 at 23:00, then 55, 84, 95, 98 through the small hours) two bars
with a real range instead of a flat carry.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Sequence
from pathlib import Path

import pmx
from pmx.data.loader import (
    MARKETS_DIR,
    dataset_files,
    dataset_hash_of,
    load_dataset,
    write_canonical_json,
    write_manifest,
)
from pmx.errors import SchemaError
from pmx.types import (
    CATEGORIES,
    MS_PER_DAY,
    MS_PER_HOUR,
    MS_PER_MINUTE,
    MS_PER_SECOND,
    REMOVED_FILTER_KEYS,
    RNG_ALGORITHM_VERSION,
    SAFETY_LAG_MS_DEFAULT,
    Bar,
    BuildConfig,
    BuiltBy,
    Dataset,
    DatasetCounts,
    DatasetFilters,
    DatasetManifest,
    DatasetNews,
    DatasetSplit,
    DatasetWindow,
    Market,
    MarketQuality,
    bar_of,
    bp_from_v1_cents,
    day_start_ms,
    hardness_tags_of,
    month_edges_for,
    ms_from_iso_date,
)
from pmx.v1.data.bundled import seed_dataset
from pmx.v1.data.loader import load_markets
from pmx.v1.types import Market as V1Market

#: The demo pack is daily, in USD, on a zero fee schedule, from the ``demo`` provider.
DEMO_PROVIDER = "demo"
DEMO_CURRENCY = "usd"
DEMO_FEE_SCHEDULE_ID = "demo-zero"
DEMO_INTERVAL_MIN = 1_440
DEMO_SOURCE = "reconstructed"
DEMO_DATASET_NAME = "demo_v1"
#: v1 recorded no resolution source; the pack states where the outcome came from rather than inventing
#: a venue that never traded these markets.
DEMO_RESOLUTION_SOURCE = "v1 demo pack"
#: The freeze the contract's own fixtures were built at (section 7.10). The demo pack is exempt from the
#: window rules of section 5.6 (its markets resolved between 2016 and 2024), but it still carries a
#: freeze so that the manifest has one shape for every dataset.
DEMO_FREEZE_DATE = "2026-09-07"
DEMO_NOTES = (
    "The twelve v1 demo markets migrated to v2 daily bars. The events and the outcomes are real; the "
    "price paths are reconstructed, which is why every market carries source: reconstructed, seal "
    "refuses this pack, and no claim can be made against it."
)

#: A v1 control point label is a date or a date with a time: "2016-06-24" or "2016-06-23T20:00".
_V1_INSTANT_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2})(?:T([0-9]{2}):([0-9]{2}))?$")


def parse_v1_instant(label: str) -> int:
    """A v1 price-point label as UTC epoch milliseconds.

    v1 kept the instant as text precisely so its journal had no clock; the migration is the one place
    that reads it, and it refuses anything that is not one of the two shapes v1 wrote.
    """
    match = _V1_INSTANT_RE.fullmatch(label)
    if match is None:
        raise SchemaError("not a v1 price-point label", label=label)
    day, hour, minute = match.groups()
    stamp = ms_from_iso_date(day)
    if hour is not None and minute is not None:
        stamp += int(hour) * MS_PER_HOUR + int(minute) * MS_PER_MINUTE
    return stamp


def bundled_v1_markets() -> tuple[V1Market, ...]:
    """The twelve bundled v1 markets, read through v1's own public seed-and-load path.

    ``pmx.v1`` is frozen, and its market table is private to ``bundled.py``; seeding a scratch directory
    and loading it back is the public route and it validates every market through v1's own model on the
    way, so a malformed demo market fails here rather than in the middle of a migration.
    """
    with tempfile.TemporaryDirectory(prefix="pmx-v1-seed-") as scratch:
        directory = Path(scratch)
        seed_dataset(directory)
        return tuple(load_markets(directory))


def _category_of(v1: V1Market) -> str:
    return v1.category if v1.category in CATEGORIES else "other"


def _control_points(v1: V1Market) -> tuple[tuple[int, int], ...]:
    """The v1 path as ``(t_ms, price_bp)``, ascending, with the cent-to-basis-point conversion applied."""
    points = tuple((parse_v1_instant(point.t), bp_from_v1_cents(point.price)) for point in v1.prices)
    if len(points) < 2:
        raise SchemaError("a v1 market needs at least two control points", market_id=v1.id)
    stamps = [stamp for stamp, _ in points]
    if stamps != sorted(stamps):
        raise SchemaError("v1 control points are out of order", market_id=v1.id)
    return points


def _resolved_at_ms(v1: V1Market, points: Sequence[tuple[int, int]]) -> int:
    """The settlement instant: the end of the stated resolution day, or the last control point if that
    is later.

    Two v1 markets (both election nights) carry control points after midnight of the day they are
    labelled resolved on, and the last control point is the price the outcome was known at. Truncating it
    away would break identity 3 (``final_price_bp`` is the last control point) and would throw away the
    only bar where the price actually moved, so the tape is allowed to end where the price ended.
    """
    day_end = day_start_ms(ms_from_iso_date(v1.resolved_date)) + MS_PER_DAY - MS_PER_SECOND
    return max(day_end, points[-1][0])


def _bars_from_points(points: Sequence[tuple[int, int]], *, resolved_at_ms: int) -> tuple[Bar, ...]:
    """The daily grid from the first control point's day to the resolution day, inclusive.

    A day with no control point repeats the previous close flat with no volume (section 5.2). A day with
    control points opens at the previous close, closes at its last point, and its range covers both, so
    the gap of an election night is visible in ``high``/``low`` rather than smoothed away. ``vwap`` is the
    close because the source carries no volume to weight with.
    """
    first_t_ms = bar_of(points[0][0], DEMO_INTERVAL_MIN)
    last_t_ms = bar_of(resolved_at_ms, DEMO_INTERVAL_MIN)
    by_day: dict[int, list[int]] = {}
    for stamp, price_bp in points:
        by_day.setdefault(bar_of(stamp, DEMO_INTERVAL_MIN), []).append(price_bp)
    bars: list[Bar] = []
    carried = points[0][1]
    t_ms = first_t_ms
    while t_ms <= last_t_ms:
        day_prices = by_day.get(t_ms, [])
        if day_prices:
            span = [carried, *day_prices]
            close_bp = day_prices[-1]
            bars.append(
                Bar(
                    t_ms=t_ms,
                    open_bp=carried,
                    high_bp=max(span),
                    low_bp=min(span),
                    close_bp=close_bp,
                    vwap_bp=close_bp,
                    volume_milli=0,
                    n_trades=0,
                    yes_bid_bp=None,
                    yes_ask_bp=None,
                    open_interest=None,
                )
            )
            carried = close_bp
        else:
            bars.append(
                Bar(
                    t_ms=t_ms,
                    open_bp=carried,
                    high_bp=carried,
                    low_bp=carried,
                    close_bp=carried,
                    vwap_bp=carried,
                    volume_milli=0,
                    n_trades=0,
                    yes_bid_bp=None,
                    yes_ask_bp=None,
                    open_interest=None,
                )
            )
        t_ms += MS_PER_DAY
    return tuple(bars)


#: The Wikipedia article titles each demo market is about, keyed by the v1 id, verbatim as an importer
#: would have read them (spaces, capitals and parentheses kept, per section 7.2). They are hand written
#: because v1 published no subject field and the pack is reconstructed anyway; ruling R97 records the
#: decision and the Brexit row is pinned by ``tests/fixtures/contract/market.demo-brexit-2016.json``.
#: Each tuple is sorted ascending by code point, which is the order the schema requires.
DEMO_WIKI_SUBJECTS: dict[str, tuple[str, ...]] = {
    "argentina-wc-2022": ("2022 FIFA World Cup", "Argentina national football team"),
    "brexit-2016": ("2016 United Kingdom European Union membership referendum",),
    "btc-100k-2022": ("Bitcoin", "History of bitcoin"),
    "btc-60k-2021": ("Bitcoin", "History of bitcoin"),
    "eth-merge-2022": ("Ethereum", "Proof of stake"),
    "fed-hike-mar-2022": ("Federal Open Market Committee", "Federal Reserve"),
    "gpt4-2023": ("GPT-4", "OpenAI"),
    "lk99-superconductor-2023": ("LK-99", "Room-temperature superconductor"),
    "titan-sub-found-2023": ("Titan submersible implosion",),
    "trump-2016": ("2016 United States presidential election", "Donald Trump"),
    "trump-2024": ("2024 United States presidential election", "Donald Trump"),
    "us-recession-2023": ("List of recessions in the United States", "Recession"),
}


def wiki_subjects_of(v1_id: str) -> tuple[str, ...]:
    """The subjects of :data:`DEMO_WIKI_SUBJECTS`, or ``()`` for a market the table does not name.

    A caller migrating its own v1 markets (``migrate_v1(markets=...)``) gets ``()`` rather than an error:
    the table is data about the twelve bundled markets, not a validation rule.
    """
    return DEMO_WIKI_SUBJECTS.get(v1_id, ())


def migrate_market(v1: V1Market) -> Market:
    """One v1 market as a v2 ``Market`` holding every identity of section 7.10."""
    points = _control_points(v1)
    created_at_ms = points[0][0]
    resolved_at_ms = _resolved_at_ms(v1, points)
    bars = _bars_from_points(points, resolved_at_ms=resolved_at_ms)
    return Market(
        schema_version=pmx.MARKET_SCHEMA,
        id=f"{DEMO_PROVIDER}-{v1.id}",
        provider=DEMO_PROVIDER,
        provider_id=v1.id,
        url="",
        question=v1.question,
        description="",
        category=_category_of(v1),
        tags=(),
        wiki_subjects=wiki_subjects_of(v1.id),
        currency=DEMO_CURRENCY,
        source=DEMO_SOURCE,
        created_at_ms=created_at_ms,
        # v1 published no separate close: the pack trades until the outcome is known, which is what
        # section 5.3 then makes untradable for the settling bar and the bar holding the close.
        close_at_ms=resolved_at_ms,
        resolved_at_ms=resolved_at_ms,
        resolution=v1.resolution,
        resolution_source=DEMO_RESOLUTION_SOURCE,
        event_key=None,
        interval_min=DEMO_INTERVAL_MIN,
        bars=bars,
        trades=(),
        first_price_bp=points[0][1],
        final_price_bp=bars[-1].close_bp,
        hardness_tags=hardness_tags_of(bars, resolution=v1.resolution, resolved_at_ms=resolved_at_ms),
        quality=MarketQuality(
            n_trades=0,
            unique_bettors=None,
            life_days=(resolved_at_ms - created_at_ms) // MS_PER_DAY,
            volume_milli_total=0,
            traded_bars=0,
        ),
        fee_schedule_id=DEMO_FEE_SCHEDULE_ID,
        notes=v1.notes,
    )


def migrate_markets(markets: Sequence[V1Market] | None = None) -> tuple[Market, ...]:
    """Every v1 market as a v2 market, in the canonical order of section 3."""
    source = bundled_v1_markets() if markets is None else tuple(markets)
    migrated = [migrate_market(v1) for v1 in source]
    return tuple(sorted(migrated, key=lambda market: (market.resolved_at_ms, market.id)))


def demo_manifest(
    markets: Sequence[Market],
    *,
    name: str = DEMO_DATASET_NAME,
    freeze_date: str = DEMO_FREEZE_DATE,
    notes: str = DEMO_NOTES,
) -> DatasetManifest:
    """The manifest of the demo pack: no news, every filter reporting zero, ``sealed: false``.

    The window is the pack's own life (``day_start_ms(min created_at)`` to ``max(resolved_at) + 1``) and
    the month edges are section 7.7's formula over that window, which is the exemption section 7.1 grants
    the pack and nothing more: the twelve-month window and the freeze checks are skipped, the split
    formula is not.
    """
    if not markets:
        raise SchemaError("the demo pack needs at least one market")
    window = DatasetWindow(
        start_ms=day_start_ms(min(market.created_at_ms for market in markets)),
        end_ms=max(market.resolved_at_ms for market in markets) + 1,
    )
    edges = month_edges_for(window.start_ms)
    split_train_end = edges[8]
    split_validation_end = edges[10]
    folds = [
        "train"
        if market.resolved_at_ms < split_train_end
        else "validation"
        if market.resolved_at_ms < split_validation_end
        else "sealed"
        for market in markets
    ]
    per_category: dict[str, int] = {}
    hardness: dict[str, int] = {}
    for market in markets:
        per_category[market.category] = per_category.get(market.category, 0) + 1
        for tag in market.hardness_tags:
            hardness[tag] = hardness.get(tag, 0) + 1
    build = BuildConfig(freeze_date=freeze_date, providers=(DEMO_PROVIDER,), news_sources=())
    return DatasetManifest(
        schema_version=pmx.DATASET_SCHEMA,
        name=name,
        freeze_date=freeze_date,
        freeze_ms=ms_from_iso_date(freeze_date),
        window=window,
        interval_min=DEMO_INTERVAL_MIN,
        providers=(DEMO_PROVIDER,),
        safety_lag_ms=SAFETY_LAG_MS_DEFAULT,
        filters=DatasetFilters(
            config=build.to_dict(),
            removed=dict.fromkeys(REMOVED_FILTER_KEYS, 0),
        ),
        counts=DatasetCounts(
            markets=len(markets),
            per_provider={DEMO_PROVIDER: len(markets)},
            per_category=per_category,
            resolution_yes=sum(1 for market in markets if market.resolution == 1),
            resolution_no=sum(1 for market in markets if market.resolution == 0),
            hardness_tags=hardness,
        ),
        news=DatasetNews(sources=(), n_items=0, n_linked=0),
        split=DatasetSplit(
            month_edges_ms=edges,
            train_end_ms=split_train_end,
            validation_end_ms=split_validation_end,
            n_train=folds.count("train"),
            n_validation=folds.count("validation"),
            n_sealed=folds.count("sealed"),
        ),
        files=(),
        # A placeholder digest that the write path replaces with the digest of the files it wrote. It is
        # 64 hex characters so the manifest is schema-valid at every intermediate step, and it is
        # deliberately not a plausible hash.
        dataset_hash="0" * 64,
        built_by=BuiltBy(
            pmx_version=pmx.__version__,
            contract_version=pmx.CONTRACT_VERSION,
            rng_algorithm_version=RNG_ALGORITHM_VERSION,
        ),
        sealed=False,
        notes=notes,
    )


def migrate_v1(
    out_dir: Path,
    *,
    markets: Sequence[V1Market] | None = None,
    name: str = DEMO_DATASET_NAME,
    freeze_date: str = DEMO_FREEZE_DATE,
    notes: str = DEMO_NOTES,
) -> Dataset:
    """Write ``data/demo_v1/`` (markets and manifest) and load it back, validated.

    The manifest is written twice on purpose: once to have a schema-valid file next to the markets, then
    again with the ``files`` listing and the ``dataset_hash`` of exactly the bytes that were written. The
    dataset is then loaded through the normal loader, so a migration that produced something the loader
    would refuse fails here and not on somebody else's first run.
    """
    migrated = migrate_markets(markets)
    out_dir.mkdir(parents=True, exist_ok=True)
    for market in migrated:
        write_canonical_json(out_dir / MARKETS_DIR / f"{market.id}.json", market.to_dict())
    manifest = demo_manifest(migrated, name=name, freeze_date=freeze_date, notes=notes)
    write_manifest(out_dir, manifest)
    files = dataset_files(out_dir)
    hashed = DatasetManifest(
        schema_version=manifest.schema_version,
        name=manifest.name,
        freeze_date=manifest.freeze_date,
        freeze_ms=manifest.freeze_ms,
        window=manifest.window,
        interval_min=manifest.interval_min,
        providers=manifest.providers,
        safety_lag_ms=manifest.safety_lag_ms,
        filters=manifest.filters,
        counts=manifest.counts,
        news=manifest.news,
        split=manifest.split,
        files=files,
        dataset_hash=dataset_hash_of(files),
        built_by=manifest.built_by,
        sealed=False,
        notes=manifest.notes,
    )
    write_manifest(out_dir, hashed)
    return load_dataset(out_dir, verify=True)
