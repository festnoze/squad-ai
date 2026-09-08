"""The five JSON schemas, the one resolver, and the strict pydantic models that read a dataset file.

A dataset is the only input to a run that a human wrote, so it is validated three times and each pass
catches what the others cannot (CONTRACTS_V2 sections 4.1 and 7.13):

1. **JSON Schema** (draft 2020-12) states the shape the contract publishes and that A5 hands to the
   Claude Code CLI through ``--json-schema``. It is the weakest of the three on numbers: a zero-fraction
   float such as ``3200.0`` **is** an integer to the specification, so the schema alone cannot enforce the
   float ban.
2. **Pydantic in strict mode** closes exactly that hole. ``3200.0`` and ``"3200"`` are refused where an
   integer belongs, so a price that went through a float somewhere upstream dies at load time instead of
   silently changing a hash.
3. **The loader** (``pmx.data.loader``) checks what neither can express: bar density on the grid, trade
   order, the news day key, the safety lag, the as-of rules of the background snapshots.

The schemas live **inside the package** (``src/pmx/schemas/``) and this module is the one resolver: a
path relative to the repository root does not exist in an installed ``pmx``, and A5 needs a real file at
run time. No other package builds a schema path of its own.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pmx.errors import SchemaError
from pmx.types import (
    JOURNAL_ENCODING,
    Bar,
    BuiltBy,
    DatasetCounts,
    DatasetFile,
    DatasetFilters,
    DatasetManifest,
    DatasetNews,
    DatasetSplit,
    DatasetWindow,
    Market,
    MarketQuality,
    NewsItem,
    NewsSourceCount,
    Trade,
)

#: ``src/pmx/schemas``: section 7.13, inside the package and not at the repository root.
SCHEMA_DIR: Path = Path(__file__).resolve().parent.parent / "schemas"
SCHEMA_FILES = (
    "market.v2.json",
    "news.v1.json",
    "dataset.v1.json",
    "actions.v2.json",
    "journal.v2.json",
)

PriceBp = Annotated[int, Field(ge=1, le=9_999)]
NullablePriceBp = Annotated[int, Field(ge=1, le=9_999)] | None
Ms = Annotated[int, Field(ge=0)]
NonNegInt = Annotated[int, Field(ge=0)]


def schema_path(name: str) -> Path:
    """The file the schema ``name`` lives in, for an ``--json-schema`` argv or an API response."""
    if name not in SCHEMA_FILES:
        raise SchemaError("unknown schema", name=name, known=list(SCHEMA_FILES))
    path = SCHEMA_DIR / name
    if not path.is_file():
        raise SchemaError("schema file missing from the package", name=name, path=str(path))
    return path


@lru_cache(maxsize=len(SCHEMA_FILES))
def _schema_cached(name: str) -> dict[str, object]:
    text = schema_path(name).read_text(encoding=JOURNAL_ENCODING)
    parsed: object = json.loads(text)
    if not isinstance(parsed, dict):
        raise SchemaError("schema is not a JSON object", name=name)
    return parsed


def load_schema(name: str) -> dict[str, object]:
    """The parsed schema. A deep copy, because the cache is shared and a caller that annotates a schema
    (the API does, to serve it) must not poison every later reader."""
    return copy.deepcopy(_schema_cached(name))


@lru_cache(maxsize=len(SCHEMA_FILES))
def validator_for(name: str) -> Draft202012Validator:
    """The compiled validator for one schema, built once per process."""
    schema = _schema_cached(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_against_schema(name: str, payload: object, *, where: str = "") -> None:
    """Raise ``SchemaError`` naming the first failure in document order, or return.

    The errors are sorted by path so the message is the same on every run: a validator's own iteration
    order over a ``oneOf`` is not something a test should depend on.
    """
    errors = sorted(validator_for(name).iter_errors(payload), key=lambda e: (list(e.absolute_path), e.message))
    if not errors:
        return
    first = errors[0]
    pointer = "/".join(str(part) for part in first.absolute_path)
    raise SchemaError(
        "payload fails its JSON schema",
        schema=name,
        where=where,
        at=pointer,
        detail=first.message,
        n_errors=len(errors),
    )


class _Strict(BaseModel):
    """Strict everywhere and closed everywhere: no coercion, no unknown key.

    Strictness is the point of this module. ``3200.0`` is a float that JSON Schema calls an integer, and
    a market whose price went through a float would hash differently on another machine while looking
    identical in a diff.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class BarModel(_Strict):
    t_ms: Ms
    open_bp: PriceBp
    high_bp: PriceBp
    low_bp: PriceBp
    close_bp: PriceBp
    vwap_bp: PriceBp
    volume_milli: NonNegInt
    n_trades: NonNegInt
    yes_bid_bp: NullablePriceBp
    yes_ask_bp: NullablePriceBp
    open_interest: NonNegInt | None

    def to_bar(self) -> Bar:
        return Bar(
            t_ms=self.t_ms,
            open_bp=self.open_bp,
            high_bp=self.high_bp,
            low_bp=self.low_bp,
            close_bp=self.close_bp,
            vwap_bp=self.vwap_bp,
            volume_milli=self.volume_milli,
            n_trades=self.n_trades,
            yes_bid_bp=self.yes_bid_bp,
            yes_ask_bp=self.yes_ask_bp,
            open_interest=self.open_interest,
        )


class TradeModel(_Strict):
    t_ms: Ms
    price_bp: PriceBp
    size_milli: Annotated[int, Field(ge=1)]
    side: Literal["yes", "no", "unknown"]

    def to_trade(self) -> Trade:
        return Trade(t_ms=self.t_ms, price_bp=self.price_bp, size_milli=self.size_milli, side=self.side)


class MarketQualityModel(_Strict):
    n_trades: NonNegInt
    unique_bettors: NonNegInt | None
    life_days: NonNegInt
    volume_milli_total: NonNegInt
    traded_bars: NonNegInt
    #: Absent on every market file written before the flag existed, which all carried a print tape.
    tape_kind: Literal["prints", "bars_only"] = "prints"

    def to_quality(self) -> MarketQuality:
        return MarketQuality(
            n_trades=self.n_trades,
            unique_bettors=self.unique_bettors,
            life_days=self.life_days,
            volume_milli_total=self.volume_milli_total,
            traded_bars=self.traded_bars,
            tape_kind=self.tape_kind,
        )


class MarketModel(_Strict):
    """``market.v2.json`` as a strict model. The ranges and the patterns are the schema's own, restated
    here because pydantic is the pass that refuses a float."""

    schema_version: Literal["market.v2"]
    id: str = Field(pattern=r"^(kalshi|manifold|polymarket|metaculus|demo)-[A-Za-z0-9._-]{1,96}$")
    provider: Literal["kalshi", "manifold", "polymarket", "metaculus", "demo"]
    provider_id: str = Field(min_length=1, max_length=128)
    url: str = Field(max_length=512)
    question: str = Field(min_length=1, max_length=500)
    description: str = Field(max_length=4_000)
    category: str = Field(pattern=r"^[a-z]+$")
    tags: list[str] = Field(max_length=16)
    wiki_subjects: list[str] = Field(max_length=8)
    #: One flag per subject, in the same order. An empty list beside a non-empty ``wiki_subjects`` means
    #: every subject is stated, which is what a market file written before the flag existed meant.
    wiki_subject_provenance: list[Literal["stated", "derived"]] = Field(default_factory=list, max_length=8)
    currency: Literal["usd", "mana"]
    source: Literal["imported", "reconstructed"]
    created_at_ms: Ms
    close_at_ms: Ms
    resolved_at_ms: Ms
    resolution: Literal[0, 1]
    resolution_source: str = Field(max_length=500)
    event_key: str | None = Field(default=None, max_length=128)
    interval_min: Literal[60, 1440]
    bars: list[BarModel] = Field(min_length=2)
    trades: list[TradeModel]
    first_price_bp: PriceBp
    final_price_bp: PriceBp
    hardness_tags: list[Literal["trivial", "upset", "whipsaw", "illiquid"]] = Field(max_length=4)
    quality: MarketQualityModel
    fee_schedule_id: str = Field(pattern=r"^([a-z]+-[a-z0-9]+-[0-9]{4}-[0-9]{2}|demo-zero)$")
    notes: str = Field(max_length=2_000)

    def to_market(self) -> Market:
        return Market(
            schema_version=self.schema_version,
            id=self.id,
            provider=self.provider,
            provider_id=self.provider_id,
            url=self.url,
            question=self.question,
            description=self.description,
            category=self.category,
            tags=tuple(self.tags),
            wiki_subjects=tuple(self.wiki_subjects),
            wiki_subject_provenance=tuple(self.wiki_subject_provenance),
            currency=self.currency,
            source=self.source,
            created_at_ms=self.created_at_ms,
            close_at_ms=self.close_at_ms,
            resolved_at_ms=self.resolved_at_ms,
            resolution=self.resolution,
            resolution_source=self.resolution_source,
            event_key=self.event_key,
            interval_min=self.interval_min,
            bars=tuple(bar.to_bar() for bar in self.bars),
            trades=tuple(trade.to_trade() for trade in self.trades),
            first_price_bp=self.first_price_bp,
            final_price_bp=self.final_price_bp,
            hardness_tags=tuple(self.hardness_tags),
            quality=self.quality.to_quality(),
            fee_schedule_id=self.fee_schedule_id,
            notes=self.notes,
        )


class NewsItemModel(_Strict):
    """``news.v1.json`` as a strict model."""

    schema_version: Literal["news.v1"]
    news_id: str = Field(pattern=r"^(wce|wasof|wb|gd|mfc)-[0-9]{8}-[0-9]{4}$")
    source: Literal[
        "wikipedia_current_events",
        "wikipedia_asof",
        "wayback",
        "gdelt",
        "manifold_comment",
    ]
    kind: Literal["headline", "background", "frontpage", "article", "comment"]
    published_at_ms: Ms
    revid: Annotated[int, Field(ge=1)] | None
    asof_day: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    visible_from_ms: Ms
    fetched_at_ms: Ms
    url: str = Field(max_length=1_024)
    headline: str = Field(min_length=1, max_length=300)
    text: str = Field(max_length=4_000)
    section: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,48}$")
    wiki_links: list[str] = Field(max_length=32)
    source_urls: list[str] = Field(max_length=16)
    match_ids: list[str]
    match_scores_permille: list[Annotated[int, Field(ge=0, le=1_000)]]
    lang: Literal["en"]
    author_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")

    def to_news_item(self) -> NewsItem:
        return NewsItem(
            schema_version=self.schema_version,
            news_id=self.news_id,
            source=self.source,
            kind=self.kind,
            published_at_ms=self.published_at_ms,
            revid=self.revid,
            asof_day=self.asof_day,
            visible_from_ms=self.visible_from_ms,
            fetched_at_ms=self.fetched_at_ms,
            url=self.url,
            headline=self.headline,
            text=self.text,
            section=self.section,
            wiki_links=tuple(self.wiki_links),
            source_urls=tuple(self.source_urls),
            match_ids=tuple(self.match_ids),
            match_scores_permille=tuple(self.match_scores_permille),
            lang=self.lang,
            author_key=self.author_key,
        )


class WindowModel(_Strict):
    start_ms: Ms
    end_ms: Ms


class FiltersModel(_Strict):
    config: dict[str, object]
    removed: dict[str, NonNegInt]


class CountsModel(_Strict):
    markets: NonNegInt
    per_provider: dict[str, NonNegInt]
    per_category: dict[str, NonNegInt]
    resolution_yes: NonNegInt
    resolution_no: NonNegInt
    hardness_tags: dict[str, NonNegInt]
    #: Optional so that a manifest written before ruling R98 still parses; the builder always writes it.
    illiquid_boundary_milli: dict[str, NonNegInt] = Field(default_factory=dict)
    #: The three counts the first real build showed were missing. All three are optional for the reason
    #: above: a manifest written before them still parses, and a re-seal of it keeps what it had.
    n_bars_only: NonNegInt = 0
    n_category_fallback: NonNegInt = 0
    precap_per_provider_month: dict[str, list[NonNegInt]] = Field(default_factory=dict)


class NewsSourceModel(_Strict):
    source: Literal[
        "wikipedia_current_events",
        "wikipedia_asof",
        "wayback",
        "gdelt",
        "manifold_comment",
    ]
    n_items: NonNegInt
    fetched_at_ms_min: Ms
    fetched_at_ms_max: Ms


class NewsBlockModel(_Strict):
    sources: list[NewsSourceModel]
    n_items: NonNegInt
    n_linked: NonNegInt


class SplitModel(_Strict):
    month_edges_ms: list[Ms] = Field(min_length=13, max_length=13)
    train_end_ms: Ms
    validation_end_ms: Ms
    n_train: NonNegInt
    n_validation: NonNegInt
    n_sealed: NonNegInt


class FileModel(_Strict):
    path: str = Field(pattern=r"^(markets|news|wiki_asof)/[A-Za-z0-9._/-]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: NonNegInt


class BuiltByModel(_Strict):
    pmx_version: str
    contract_version: str
    rng_algorithm_version: str


class DatasetManifestModel(_Strict):
    """``dataset.v1.json`` as a strict model."""

    schema_version: Literal["dataset.v1"]
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    freeze_date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    freeze_ms: Ms
    window: WindowModel
    interval_min: Literal[60, 1440]
    providers: list[Literal["kalshi", "manifold", "polymarket", "metaculus", "demo"]] = Field(min_length=1)
    safety_lag_ms: Ms
    filters: FiltersModel
    counts: CountsModel
    news: NewsBlockModel
    split: SplitModel
    files: list[FileModel]
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    built_by: BuiltByModel
    sealed: bool
    notes: str = Field(max_length=4_000)

    def to_manifest(self) -> DatasetManifest:
        return DatasetManifest(
            schema_version=self.schema_version,
            name=self.name,
            freeze_date=self.freeze_date,
            freeze_ms=self.freeze_ms,
            window=DatasetWindow(start_ms=self.window.start_ms, end_ms=self.window.end_ms),
            interval_min=self.interval_min,
            providers=tuple(self.providers),
            safety_lag_ms=self.safety_lag_ms,
            filters=DatasetFilters(config=dict(self.filters.config), removed=dict(self.filters.removed)),
            counts=DatasetCounts(
                markets=self.counts.markets,
                per_provider=dict(self.counts.per_provider),
                per_category=dict(self.counts.per_category),
                resolution_yes=self.counts.resolution_yes,
                resolution_no=self.counts.resolution_no,
                hardness_tags=dict(self.counts.hardness_tags),
                # Carried through, because ``seal`` rewrites the manifest from this object and a field
                # dropped here would be a number the seal silently deleted.
                illiquid_boundary_milli=dict(self.counts.illiquid_boundary_milli),
                n_bars_only=self.counts.n_bars_only,
                n_category_fallback=self.counts.n_category_fallback,
                precap_per_provider_month={
                    provider: tuple(months)
                    for provider, months in self.counts.precap_per_provider_month.items()
                },
            ),
            news=DatasetNews(
                sources=tuple(
                    NewsSourceCount(
                        source=source.source,
                        n_items=source.n_items,
                        fetched_at_ms_min=source.fetched_at_ms_min,
                        fetched_at_ms_max=source.fetched_at_ms_max,
                    )
                    for source in self.news.sources
                ),
                n_items=self.news.n_items,
                n_linked=self.news.n_linked,
            ),
            split=DatasetSplit(
                month_edges_ms=tuple(self.split.month_edges_ms),
                train_end_ms=self.split.train_end_ms,
                validation_end_ms=self.split.validation_end_ms,
                n_train=self.split.n_train,
                n_validation=self.split.n_validation,
                n_sealed=self.split.n_sealed,
            ),
            files=tuple(
                DatasetFile(path=entry.path, sha256=entry.sha256, bytes=entry.bytes) for entry in self.files
            ),
            dataset_hash=self.dataset_hash,
            built_by=BuiltBy(
                pmx_version=self.built_by.pmx_version,
                contract_version=self.built_by.contract_version,
                rng_algorithm_version=self.built_by.rng_algorithm_version,
            ),
            sealed=self.sealed,
            notes=self.notes,
        )


def market_from_payload(payload: object, *, where: str = "") -> Market:
    """Schema, then strict model, then the frozen dataclass. The one door into a ``Market`` from JSON."""
    validate_against_schema("market.v2.json", payload, where=where)
    return _validated(MarketModel, payload, where=where).to_market()


def news_item_from_payload(payload: object, *, where: str = "") -> NewsItem:
    """The one door into a ``NewsItem`` from JSON."""
    validate_against_schema("news.v1.json", payload, where=where)
    return _validated(NewsItemModel, payload, where=where).to_news_item()


def manifest_from_payload(payload: object, *, where: str = "") -> DatasetManifest:
    """The one door into a ``DatasetManifest`` from JSON."""
    validate_against_schema("dataset.v1.json", payload, where=where)
    return _validated(DatasetManifestModel, payload, where=where).to_manifest()


def _validated[ModelT: BaseModel](model: type[ModelT], payload: object, *, where: str) -> ModelT:
    """``model.model_validate`` with the failure rendered as a ``SchemaError``.

    Pydantic's own exception carries the whole error list, which is what a human wants and not what an
    engine wants: the taxonomy of section 13.1 says a bad file is a ``SchemaError``, so the detail is
    flattened into context and the type stays one.
    """
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        pointer = "/".join(str(part) for part in first["loc"])
        raise SchemaError(
            "payload fails its strict model",
            model=model.__name__,
            where=where,
            at=pointer,
            detail=first["msg"],
            n_errors=exc.error_count(),
        ) from exc
