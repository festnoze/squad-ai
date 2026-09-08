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
    PRICE_TICKS_MAX,
    Bar,
    BuiltBy,
    CashEvent,
    ContinuousInstrument,
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
    Session,
    SessionCalendar,
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
    # Amendment C1b's four (section 17.9, applied by gate G2).
    "instrument.v1.json",
    "cash_event.v1.json",
    "session_calendar.v1.json",
    "forecast.v1.json",
)

PriceBp = Annotated[int, Field(ge=1, le=9_999)]
NullablePriceBp = Annotated[int, Field(ge=1, le=9_999)] | None
PriceTicks = Annotated[int, Field(ge=1, le=PRICE_TICKS_MAX)]
NullablePriceTicks = Annotated[int, Field(ge=1, le=PRICE_TICKS_MAX)] | None
Ms = Annotated[int, Field(ge=0)]
NonNegInt = Annotated[int, Field(ge=0)]
ProviderLiteral = Literal[
    "kalshi",
    "manifold",
    "polymarket",
    "metaculus",
    "demo",
    "binance",
    "kraken",
    "coinbase",
    "bybit",
    "xnys",
    "xnas",
    "arcx",
    "xcme",
    "xnym",
    "xcec",
    "xcbt",
    "otcfx",
]
VendorLiteral = Literal[
    "kalshi",
    "manifold",
    "polymarket",
    "metaculus",
    "demo",
    "binance",
    "kraken",
    "coinbase",
    "bybit",
    "yahoo",
    "frankfurter",
    "ecb",
]
INSTRUMENT_ID_PATTERN = (
    r"^(kalshi|manifold|polymarket|metaculus|demo|binance|kraken|coinbase|bybit|xnys|xnas|arcx|xcme|xnym|"
    r"xcec|xcbt|otcfx)-[A-Za-z0-9._-]{1,96}$"
)
SCHEDULE_ID_PATTERN = r"^([a-z]+-[a-z0-9]+-[0-9]{4}-[0-9]{2}|demo-zero)$"


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
    id: str = Field(pattern=INSTRUMENT_ID_PATTERN)
    provider: ProviderLiteral
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
    currency: Literal["usd", "mana", "usdt", "eur", "jpy"]
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
        "edgar",
        "fred",
        "cboe",
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
    #: Amendment C1b (17.6): instruments counted per fold, optional so a binary manifest still parses.
    n_instruments_train: NonNegInt = 0
    n_instruments_validation: NonNegInt = 0
    n_instruments_sealed: NonNegInt = 0


class InstrumentsBlockModel(_Strict):
    """The ``instruments`` block of 7.8 (amendment C1b): counts of what ``instruments/`` and ``calendars/`` hold."""

    per_kind: dict[str, NonNegInt]
    per_provider: dict[str, NonNegInt]
    per_vendor: dict[str, NonNegInt]
    n_cash_events: dict[str, dict[str, NonNegInt]]
    n_calendars: NonNegInt


class SchedulesBlockModel(_Strict):
    """The ``schedules`` block of 7.8 (amendment C1b): the schedule ids the dataset's instruments name."""

    fee: list[str]
    borrow: list[str]
    carry: list[str]


class FileModel(_Strict):
    path: str = Field(pattern=r"^(markets|news|wiki_asof|clusters|instruments|calendars)/[A-Za-z0-9._/-]+$")
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
    providers: list[ProviderLiteral] = Field(min_length=1)
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
    #: The optional blocks of 7.8: amendment C1's ``clusters`` and ``impact`` are read as opaque mappings
    #: (their consumers land in waves 7 and 8); amendment C1b's three are typed here (gate G2).
    clusters: dict[str, object] | None = None
    impact: dict[str, object] | None = None
    kinds: list[Literal["binary", "spot_crypto", "perp", "fx", "equity", "future"]] = Field(default_factory=list)
    instruments: InstrumentsBlockModel | None = None
    schedules: SchedulesBlockModel | None = None

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
                n_instruments_train=self.split.n_instruments_train,
                n_instruments_validation=self.split.n_instruments_validation,
                n_instruments_sealed=self.split.n_instruments_sealed,
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
            clusters=None if self.clusters is None else dict(self.clusters),
            impact=None if self.impact is None else dict(self.impact),
            kinds=tuple(self.kinds),
            instruments=None
            if self.instruments is None
            else {
                "per_kind": dict(self.instruments.per_kind),
                "per_provider": dict(self.instruments.per_provider),
                "per_vendor": dict(self.instruments.per_vendor),
                "n_cash_events": {"per_kind": dict(self.instruments.n_cash_events.get("per_kind", {}))},
                "n_calendars": self.instruments.n_calendars,
            },
            schedules=None
            if self.schedules is None
            else {
                "fee": tuple(self.schedules.fee),
                "borrow": tuple(self.schedules.borrow),
                "carry": tuple(self.schedules.carry),
            },
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


# --------------------------------------------------------------------------------------------------
# Amendment C1b's three file shapes (sections 17.1 to 17.3; landed by gate G2)
# --------------------------------------------------------------------------------------------------
class SessionModel(_Strict):
    open_ms: Ms
    close_ms: Ms


class SessionCalendarModel(_Strict):
    """``session_calendar.v1.json`` as a strict model (section 17.2)."""

    schema_version: Literal["session_calendar.v1"]
    calendar_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    description: str = Field(max_length=500)
    source_url: str = Field(max_length=512)
    as_of_date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    window: WindowModel
    sessions: list[SessionModel] = Field(min_length=1)
    holidays: list[str]

    def to_calendar(self) -> SessionCalendar:
        return SessionCalendar(
            calendar_id=self.calendar_id,
            description=self.description,
            source_url=self.source_url,
            as_of_date=self.as_of_date,
            window=DatasetWindow(start_ms=self.window.start_ms, end_ms=self.window.end_ms),
            sessions=tuple(Session(open_ms=s.open_ms, close_ms=s.close_ms) for s in self.sessions),
            holidays=tuple(self.holidays),
        )


class CashEventModel(_Strict):
    """``cash_event.v1.json`` as a strict model (section 17.3). ``detail`` is integers and strings only."""

    schema_version: Literal["cash_event.v1"]
    cash_event_id: str = Field(pattern=r"^ce-[0-9a-f]{16}$")
    market_id: str = Field(pattern=INSTRUMENT_ID_PATTERN)
    kind: Literal["funding", "dividend", "split", "roll", "borrow_fee", "carry", "forced_flat"]
    t_ms: Ms
    origin: Literal["data", "engine"]
    source_url: str = Field(max_length=512)
    detail: dict[str, int | str]

    def to_cash_event(self) -> CashEvent:
        return CashEvent(
            cash_event_id=self.cash_event_id,
            market_id=self.market_id,
            kind=self.kind,
            t_ms=self.t_ms,
            origin=self.origin,
            source_url=self.source_url,
            detail=dict(self.detail),
        )


class InstrumentBarModel(_Strict):
    """The **file** shape of a bar (``instrument.v1.json#/$defs/bar``, ruling R173): ``_ticks`` fields,
    mapped onto the one in-memory ``Bar`` field by field."""

    t_ms: Ms
    open_ticks: PriceTicks
    high_ticks: PriceTicks
    low_ticks: PriceTicks
    close_ticks: PriceTicks
    vwap_ticks: PriceTicks
    volume_milli: NonNegInt
    n_trades: NonNegInt
    bid_ticks: NullablePriceTicks
    ask_ticks: NullablePriceTicks
    open_interest_milli: NonNegInt | None

    def to_bar(self) -> Bar:
        return Bar(
            t_ms=self.t_ms,
            open_bp=self.open_ticks,
            high_bp=self.high_ticks,
            low_bp=self.low_ticks,
            close_bp=self.close_ticks,
            vwap_bp=self.vwap_ticks,
            volume_milli=self.volume_milli,
            n_trades=self.n_trades,
            yes_bid_bp=self.bid_ticks,
            yes_ask_bp=self.ask_ticks,
            open_interest=self.open_interest_milli,
        )


class InstrumentTradeModel(_Strict):
    t_ms: Ms
    price_ticks: PriceTicks
    size_milli: Annotated[int, Field(ge=1)]
    side: Literal["buy", "sell", "unknown"]

    def to_trade(self) -> Trade:
        return Trade(t_ms=self.t_ms, price_bp=self.price_ticks, size_milli=self.size_milli, side=self.side)


class InstrumentQualityModel(_Strict):
    n_trades: NonNegInt
    life_days: NonNegInt
    volume_milli_total: NonNegInt
    traded_bars: NonNegInt
    tape_kind: Literal["prints", "bars_only"]

    def to_quality(self) -> MarketQuality:
        return MarketQuality(
            n_trades=self.n_trades,
            unique_bettors=None,
            life_days=self.life_days,
            volume_milli_total=self.volume_milli_total,
            traded_bars=self.traded_bars,
            tape_kind=self.tape_kind,
        )


class InstrumentModel(_Strict):
    """``instrument.v1.json`` as a strict model (section 17.1). The kind table's cross-field rules are
    the schema's ``allOf`` and ``ContinuousInstrument.__post_init__``'s; this pass refuses the floats."""

    schema_version: Literal["instrument.v1"]
    id: str = Field(pattern=INSTRUMENT_ID_PATTERN)
    provider: ProviderLiteral
    vendor: VendorLiteral
    symbol: str = Field(min_length=1, max_length=64)
    kind: Literal["spot_crypto", "perp", "fx", "equity", "future"]
    currency: str = Field(pattern=r"^[a-z]{3,5}$")
    tick_size_micro: Annotated[int, Field(ge=1, le=10**9)]
    point_value_micro: Annotated[int, Field(ge=1, le=10**12)]
    session_calendar_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    fee_schedule_id: str = Field(pattern=SCHEDULE_ID_PATTERN)
    borrow_schedule_id: str | None = Field(default=None, pattern=SCHEDULE_ID_PATTERN)
    carry_schedule_id: str | None = Field(default=None, pattern=SCHEDULE_ID_PATTERN)
    listed_at_ms: Ms
    delisted_at_ms: NonNegInt | None
    short_allowed: bool
    interval_min: Literal[60, 1440]
    url: str = Field(max_length=512)
    description: str = Field(max_length=4_000)
    category: Literal["crypto", "finance", "economics", "other"]
    tags: list[str] = Field(max_length=16)
    twins: list[str] = Field(max_length=16)
    underlying_id: str | None = Field(default=None, pattern=INSTRUMENT_ID_PATTERN)
    roll_source: Literal["venue", "vendor"] | None
    first_price_ticks: PriceTicks
    bars: list[InstrumentBarModel] = Field(min_length=1)
    trades: list[InstrumentTradeModel]
    quality: InstrumentQualityModel
    cash_events: list[CashEventModel]
    source: Literal["imported"]
    notes: str = Field(max_length=2_000)

    def to_instrument(self) -> ContinuousInstrument:
        return ContinuousInstrument(
            id=self.id,
            provider=self.provider,
            vendor=self.vendor,
            symbol=self.symbol,
            kind=self.kind,
            currency=self.currency,
            tick_size_micro=self.tick_size_micro,
            point_value_micro=self.point_value_micro,
            session_calendar_id=self.session_calendar_id,
            fee_schedule_id=self.fee_schedule_id,
            borrow_schedule_id=self.borrow_schedule_id,
            carry_schedule_id=self.carry_schedule_id,
            listed_at_ms=self.listed_at_ms,
            delisted_at_ms=self.delisted_at_ms,
            short_allowed=self.short_allowed,
            interval_min=self.interval_min,
            bars=tuple(bar.to_bar() for bar in self.bars),
            trades=tuple(trade.to_trade() for trade in self.trades),
            schema_version=self.schema_version,
            url=self.url,
            description=self.description,
            category=self.category,
            tags=tuple(self.tags),
            twins=tuple(self.twins),
            underlying_id=self.underlying_id,
            roll_source=self.roll_source,
            first_price_ticks=self.first_price_ticks,
            quality=self.quality.to_quality(),
            cash_events=tuple(event.to_cash_event() for event in self.cash_events),
            source=self.source,
            notes=self.notes,
        )


def instrument_from_payload(payload: object, *, where: str = "") -> ContinuousInstrument:
    """The one door into a ``ContinuousInstrument`` from JSON (schema, strict model, dataclass)."""
    validate_against_schema("instrument.v1.json", payload, where=where)
    return _validated(InstrumentModel, payload, where=where).to_instrument()


def session_calendar_from_payload(payload: object, *, where: str = "") -> SessionCalendar:
    """The one door into a ``SessionCalendar`` from JSON."""
    validate_against_schema("session_calendar.v1.json", payload, where=where)
    return _validated(SessionCalendarModel, payload, where=where).to_calendar()


def cash_event_from_payload(payload: object, *, where: str = "") -> CashEvent:
    """The one door into a standalone ``CashEvent`` record from JSON (``cash_event.v1.json``)."""
    validate_against_schema("cash_event.v1.json", payload, where=where)
    return _validated(CashEventModel, payload, where=where).to_cash_event()
