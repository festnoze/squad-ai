"""The ``pmx data`` command group: import, news fetch, build, refresh, seal, verify, status, migrate-v1.

This is the one place in pmx where a network, a filter and a file meet, and it is deliberately split in
two halves. The **fetch** half (``import``, ``news fetch``) talks to a provider through the one throttled,
cached HTTP client of section 7.11 and writes what came back into a *staging* directory, one canonical JSON
document per line, unfiltered. The **build** half (``build``, ``refresh``) reads staging, applies the window
and the quality filters, tags, splits, writes and hashes a dataset, and opens no socket at all.

The reason for the split is reproducibility with a receipt. A build that fetched while it filtered could
not be re-run: the provider's answer would have moved, and "why did this market disappear" would have no
answer. With staging on disk, ``pmx data build --offline`` rebuilds the same dataset byte for byte from the
same raw answers, which is what makes the manifest's filter counts evidence rather than a claim.

Every sibling of wave 1 is reached by name and late: the importers and fetchers of section 7.12, D2's HTTP
client, D1's loader and migration. That is what lets this group parse its arguments, print its help and
build from staging while a provider module is still being written, and it is why the base URL of each
provider is read from the importer that owns it rather than copied here.

``register`` exists so U4's ``pmx`` parser can mount this group in wave 5 without either file importing the
other's internals, and ``main`` exists so the group runs today as ``python -m pmx.cli_data ...``.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from pmx.data.builder import (
    BuildResult,
    as_plain_dict,
    build_config_from_manifest,
    build_dataset_from_payloads,
)
from pmx.errors import InvalidConfigError, NotConfiguredError, PmxError
from pmx.types import (
    MS_PER_DAY,
    SAFETY_LAG_MS_DEFAULT,
    SUBJECT_STATED,
    BuildConfig,
    DatasetManifest,
    day_key,
    iso_date_from_ms,
    ms_from_iso_date,
)

__all__ = ["build_parser", "main", "register"]


class Importer(Protocol):
    """The one importer shape of section 7.12. Every provider extension is passed only when its own
    signature declares it (see ``_supported``)."""

    def __call__(
        self,
        *,
        client: object,
        window_start_ms: int,
        window_end_ms: int,
        freeze_ms: int,
        limit: int | None = ...,
    ) -> Sequence[object]: ...


class DayFetcher(Protocol):
    """A news fetcher that answers for one UTC day (section 7.12)."""

    def __call__(self, *, client: object, day_start_ms: int) -> Sequence[object]: ...


class CommentFetcher(Protocol):
    """The Manifold comment fetcher, which answers per market (section 7.12)."""

    def __call__(self, *, client: object, market: object) -> Sequence[object]: ...


class AsofFetcher(Protocol):
    """The point-in-time article fetcher, which answers per title and per day (section 7.12)."""

    def __call__(self, *, client: object, title: str, asof_day: str, market_id: str) -> Sequence[object]: ...


#: ``provider -> (module, importer, base-url constant, api-key environment variable)``. The base URL lives
#: in the importer that owns the provider (``KALSHI_BASE_URL`` and friends), so this table names it rather
#: than repeating a host: a second copy of a base URL is a second thing to get wrong the day a venue moves.
IMPORTER_TARGETS: dict[str, tuple[str, str, str, str | None]] = {
    "kalshi": ("pmx.data.importers.kalshi", "import_kalshi", "KALSHI_BASE_URL", "PMX_KALSHI_API_KEY"),
    "manifold": ("pmx.data.importers.manifold", "import_manifold", "MANIFOLD_BASE_URL", None),
    "polymarket": ("pmx.data.importers.polymarket", "import_polymarket", "GAMMA_BASE_URL", None),
    "metaculus": ("pmx.data.importers.metaculus", "import_metaculus", "METACULUS_BASE_URL", "PMX_METACULUS_TOKEN"),
}

#: ``source -> (module, fetcher)`` for the three sources that answer per day (section 7.12).
DAY_FETCHER_TARGETS: dict[str, tuple[str, str]] = {
    "wikipedia_current_events": ("pmx.data.news.wikipedia_current_events", "fetch_wikipedia_current_events"),
    "wayback": ("pmx.data.news.wayback", "fetch_wayback"),
    "gdelt": ("pmx.data.news.gdelt", "fetch_gdelt"),
}
COMMENT_FETCHER_TARGET = ("pmx.data.news.manifold_comments", "fetch_comments")
ASOF_FETCHER_TARGET = ("pmx.data.news.wikipedia_asof", "fetch_wikipedia_asof")

#: ``source -> module`` for the base URL of each news host. Ruling R96 gave every news module a
#: ``BASE_URL`` constant, so the host is read from the module that documents it rather than restated here:
#: a second spelling had already drifted (the Wayback module said ``http``, this table said ``https``).
NEWS_BASE_URL_MODULES = {
    "wikipedia_current_events": "pmx.data.news.wikipedia_current_events",
    "wikipedia_asof": "pmx.data.news.wikipedia_asof",
    "wayback": "pmx.data.news.wayback",
    "gdelt": "pmx.data.news.gdelt",
}

#: The throttle each source asks for. GDELT answers 429 below one request every five seconds and its
#: fetcher refuses a faster client outright; the Wayback CDX endpoint is asked politely at one every two.
NEWS_MIN_INTERVAL_MS = {
    "wikipedia_current_events": 1_000,
    "wikipedia_asof": 1_000,
    "wayback": 2_000,
    "gdelt": 5_000,
    "manifold_comment": 1_000,
}

DEFAULT_DATASETS = Path("data/datasets")
DEFAULT_DEMO_OUT = Path("data/demo_v1")
DEFAULT_DATASET_NAME = "default"

#: Staging and the HTTP cache both live inside the dataset directory: section 7.11 puts the cache at
#: ``data/datasets/<name>/cache/``, and neither belongs in the dataset hash (section 4.3 walks
#: ``markets/``, ``news/`` and ``wiki_asof/`` and nothing else), so the git-ignored ``data/datasets/*``
#: already covers both and no new ignore rule is needed for a year of raw provider answers.
STAGING_DIR = "staging"

#: One background snapshot per this many days of a market's life (section 7.1).
ASOF_EVERY_DAYS = 7

MARKETS_DIR = "markets"
NEWS_DIR = "news"
CACHE_DIR = "cache"


def _default_staging(name: str) -> Path:
    return DEFAULT_DATASETS / name / STAGING_DIR


def _default_cache(staging: Path) -> Path:
    """The cache beside staging, inside the dataset directory (section 7.11)."""
    return staging.parent / CACHE_DIR


# --------------------------------------------------------------------------------------------------
# Late binding of the siblings and of the HTTP client
# --------------------------------------------------------------------------------------------------
def _resolve(module_name: str, attribute: str) -> object:
    module = importlib.import_module(module_name)
    if not hasattr(module, attribute):
        raise InvalidConfigError("a contracted entry point is missing", module=module_name, name=attribute)
    return getattr(module, attribute)


def _supported(function: object, candidates: Mapping[str, object]) -> dict[str, object]:
    """The subset of ``candidates`` the callable actually declares.

    Section 7.12 fixes five keyword arguments for an importer and two or three for a fetcher, and the real
    modules add their own beyond that (``interval_min`` on Kalshi and Polymarket, ``safety_lag_ms`` on every
    fetcher, ``index_offset_by_day`` on the comment fetcher). Passing one to a module that does not declare
    it would be a TypeError, and not passing it where it exists would silently build the wrong grid or the
    wrong lag, so the caller asks.
    """
    try:
        signature = inspect.signature(cast(Callable[..., object], function))
    except (TypeError, ValueError):  # pragma: no cover - a C callable cannot appear here
        return {}
    names = set(signature.parameters)
    return {key: value for key, value in candidates.items() if key in names}


def _load_importer(provider: str) -> Importer:
    if provider not in IMPORTER_TARGETS:
        raise InvalidConfigError("no importer for this provider", provider=provider)
    module_name, attribute, _base, _key = IMPORTER_TARGETS[provider]
    return cast(Importer, _resolve(module_name, attribute))


def _importer_base_url(provider: str) -> str:
    module_name, _attribute, base_constant, _key = IMPORTER_TARGETS[provider]
    return cast(str, _resolve(module_name, base_constant))


def _news_base_url(source: str) -> str:
    """The host of ``source``, read from the module that owns it (ruling R96)."""
    if source not in NEWS_BASE_URL_MODULES:
        raise InvalidConfigError("no news host for this source", source=source)
    return cast(str, _resolve(NEWS_BASE_URL_MODULES[source], "BASE_URL"))


def _load_day_fetcher(source: str) -> DayFetcher:
    if source not in DAY_FETCHER_TARGETS:
        raise InvalidConfigError("no per-day fetcher for this source", source=source)
    module_name, attribute = DAY_FETCHER_TARGETS[source]
    return cast(DayFetcher, _resolve(module_name, attribute))


def _user_agent() -> str:
    """``USER_AGENT_TEMPLATE`` filled with the version and the contact address of section 7.11.

    Wikipedia answers 403 to a generic agent string, so a missing contact address is a configuration error
    and not something to paper over with a default.
    """
    http = importlib.import_module("pmx.data.importers._http")
    contact_env = cast(str, http.USER_AGENT_CONTACT_ENV)
    contact = os.environ.get(contact_env, "").strip()
    if not contact:
        raise NotConfiguredError("a fetcher needs a contact address in its User-Agent", variable=contact_env)
    from pmx import __version__ as pmx_version

    return cast(str, http.USER_AGENT_TEMPLATE).format(version=pmx_version, contact=contact)


def _make_client(*, base_url: str, cache_dir: Path, min_interval_ms: int, api_key: str | None = None) -> object:
    http = importlib.import_module("pmx.data.importers._http")
    client_cls = cast(Callable[..., object], http.HttpClient)
    return client_cls(
        base_url=base_url,
        user_agent=_user_agent(),
        min_interval_ms=min_interval_ms,
        cache_dir=cache_dir,
        api_key=api_key,
    )


def _close(client: object) -> None:
    closer = getattr(client, "close", None)
    if callable(closer):
        closer()


def _market_from_payload(payload: Mapping[str, object]) -> object:
    """A staged document back into a ``Market``, through D1's one door (``pmx.data.schema``)."""
    parser = cast(Callable[..., object], _resolve("pmx.data.schema", "market_from_payload"))
    return parser(dict(payload), where="staged market")


# --------------------------------------------------------------------------------------------------
# Staging: one canonical JSON document per line, exactly what the provider's answer mapped to
# --------------------------------------------------------------------------------------------------
def _write_jsonl(path: Path, payloads: Sequence[Mapping[str, object]]) -> int:
    writer = cast(Callable[..., int], _resolve("pmx.data.loader", "write_canonical_jsonl"))
    writer(path, list(payloads))
    return len(payloads)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read a staged file back, refusing the two byte-level accidents section 4.2 names."""
    rows: list[dict[str, object]] = []
    with open(path, encoding="utf-8", newline="\n") as handle:
        for lineno, line in enumerate(handle, start=1):
            if line.startswith("﻿"):
                raise InvalidConfigError("a staged file carries a byte order mark", path=str(path))
            stripped = line.strip("\n")
            if not stripped:
                continue
            if "\r" in stripped:
                raise InvalidConfigError("a staged line carries a carriage return", path=str(path), line=lineno)
            parsed = json.loads(stripped)
            if not isinstance(parsed, dict):
                raise InvalidConfigError("a staged line is not a JSON object", path=str(path), line=lineno)
            rows.append({str(key): value for key, value in parsed.items()})
    return rows


def _staged_markets(staging: Path, providers: Sequence[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for provider in providers:
        path = staging / MARKETS_DIR / f"{provider}.jsonl"
        if not path.exists():
            raise InvalidConfigError(
                "no staged import for this provider (run pmx data import first)",
                provider=provider,
                path=str(path),
            )
        rows.extend(_read_jsonl(path))
    return rows


def _staged_news(staging: Path) -> list[dict[str, object]]:
    base = staging / NEWS_DIR
    if not base.exists():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(base.glob("*.jsonl")):
        rows.extend(_read_jsonl(path))
    return rows


def _restamp_visibility(payloads: Sequence[Mapping[str, object]], *, safety_lag_ms: int) -> list[dict[str, object]]:
    """Stamp ``visible_from_ms = published_at_ms + safety_lag_ms`` on freshly fetched items.

    Section 7.12 says a fetcher returns items already carrying "the caller's ``safety_lag_ms``" while no
    fetcher signature in that section carries the lag; the real fetchers take it as an extension, which
    ``_supported`` passes. This normalisation is the belt beside that brace: the builder recomputes the
    stamp and refuses a mismatch, so the staged bytes must agree with the build's lag whatever a fetcher
    defaulted to.
    """
    out: list[dict[str, object]] = []
    for payload in payloads:
        item = dict(payload)
        item["visible_from_ms"] = _int_or_zero(item, "published_at_ms") + safety_lag_ms
        out.append(item)
    return out


def _int_or_zero(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _str_or_empty(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _news_sort_key(payload: Mapping[str, object]) -> tuple[int, str]:
    """``(published_at_ms, news_id)``, the order a news file is written in (section 3)."""
    return (_int_or_zero(payload, "published_at_ms"), _str_or_empty(payload, "news_id"))


def _market_sort_key(payload: Mapping[str, object]) -> tuple[int, str]:
    """``(resolved_at_ms, id)``, the canonical order of the markets of a dataset (section 3).

    Staging is written in it so a diff between two imports is readable, and the builder sorts again: what
    an importer hands back is its business, what lands on disk is the contract's.
    """
    return (_int_or_zero(payload, "resolved_at_ms"), _str_or_empty(payload, "id"))


# --------------------------------------------------------------------------------------------------
# Windows and reporting
# --------------------------------------------------------------------------------------------------
def _window(freeze_date: str, window_days: int) -> tuple[int, int, int]:
    """``(window_start_ms, window_end_ms, freeze_ms)`` of section 5.6, from the freeze date."""
    freeze_ms = ms_from_iso_date(freeze_date)
    return freeze_ms - window_days * MS_PER_DAY, freeze_ms - MS_PER_DAY, freeze_ms


def _pairs(mapping: Mapping[str, int]) -> str:
    return " ".join(f"{key}={value}" for key, value in sorted(mapping.items())) or "none"


def _print_manifest(manifest: DatasetManifest, path: Path, *, extra: Sequence[str] = ()) -> None:
    """The one rendering of a dataset, used by ``build``, ``refresh`` and ``status``."""
    print(f"dataset {manifest.name} at {path}")
    print(f"  sealed     {'true' if manifest.sealed else 'false'}")
    print(f"  freeze     {manifest.freeze_date}  interval {manifest.interval_min} min")
    print(
        "  window     "
        f"{iso_date_from_ms(manifest.window.start_ms)} .. {iso_date_from_ms(manifest.window.end_ms)}"
    )
    counts = manifest.counts
    print(f"  markets    {counts.markets}  yes {counts.resolution_yes}  no {counts.resolution_no}")
    print(f"  provider   {_pairs(dict(counts.per_provider))}")
    print(f"  category   {_pairs(dict(counts.per_category))}")
    print(f"  hardness   {_pairs(dict(counts.hardness_tags))}")
    print(f"  tape       bars_only {counts.n_bars_only}  category fallback {counts.n_category_fallback}")
    for provider, months in sorted(counts.precap_per_provider_month.items()):
        print(f"  precap     {provider:<12} {' '.join(str(count) for count in months)}")
    print(f"  removed    {_pairs(dict(manifest.filters.removed))}")
    split = manifest.split
    print(f"  split      train {split.n_train}  validation {split.n_validation}  sealed {split.n_sealed}")
    print(f"  news       {manifest.news.n_items} items, {manifest.news.n_linked} linked")
    for source in manifest.news.sources:
        print(f"    {source.source:<26} {source.n_items}")
    print(f"  files      {len(manifest.files)}")
    print(f"  hash       {manifest.dataset_hash}")
    for line in extra:
        if line:
            print(line)


# --------------------------------------------------------------------------------------------------
# import
# --------------------------------------------------------------------------------------------------
def _import_provider(
    provider: str,
    *,
    staging: Path,
    cache_dir: Path,
    freeze_date: str,
    window_days: int,
    interval_min: int,
    limit: int | None,
    min_interval_ms: int,
    series_allow_list: Sequence[str] = (),
    opened_early_days: int = 90,
    min_life_days: int = 0,
) -> int:
    window_start_ms, window_end_ms, freeze_ms = _window(freeze_date, window_days)
    importer = _load_importer(provider)
    _module, _name, _base, key_env = IMPORTER_TARGETS[provider]
    client = _make_client(
        base_url=_importer_base_url(provider),
        cache_dir=cache_dir / provider,
        min_interval_ms=min_interval_ms,
        api_key=os.environ.get(key_env) if key_env else None,
    )
    try:
        markets = importer(
            client=client,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            freeze_ms=freeze_ms,
            limit=limit,
            **_supported(
                importer,
                {
                    "interval_min": interval_min,
                    "series_allow_list": tuple(series_allow_list),
                    # The importer's creation floor is the build's own ``opened_early_days``, so the
                    # walk stops exactly where the filter of section 7.4 would drop what it found. The
                    # life floor is the same idea for the same reason: a row the ``min_life`` filter
                    # will remove costs two requests of the fetch budget and lands in no dataset.
                    "created_floor_ms": window_start_ms - opened_early_days * MS_PER_DAY,
                    "min_life_days": min_life_days,
                },
            ),
        )
    finally:
        _close(client)
    payloads = sorted((as_plain_dict(market) for market in markets), key=_market_sort_key)
    written = _write_jsonl(staging / MARKETS_DIR / f"{provider}.jsonl", payloads)
    print(f"staged {written} {provider} markets to {staging / MARKETS_DIR / f'{provider}.jsonl'}")
    return written


def _cmd_import(args: argparse.Namespace) -> int:
    staging = Path(args.staging)
    _import_provider(
        cast(str, args.provider),
        staging=staging,
        cache_dir=Path(args.cache_dir) if args.cache_dir else _default_cache(staging),
        freeze_date=cast(str, args.freeze),
        window_days=int(args.window_days),
        interval_min=int(args.interval_min),
        limit=args.limit,
        min_interval_ms=int(args.min_interval_ms),
        series_allow_list=_csv(args.kalshi_series),
        opened_early_days=int(args.opened_early_days),
        min_life_days=int(args.min_life_days),
    )
    return 0


# --------------------------------------------------------------------------------------------------
# news fetch
# --------------------------------------------------------------------------------------------------
def _fetch_days(
    source: str,
    *,
    cache_dir: Path,
    days: Sequence[int],
    safety_lag_ms: int,
) -> list[dict[str, object]]:
    fetcher = _load_day_fetcher(source)
    client = _make_client(
        base_url=_news_base_url(source),
        cache_dir=cache_dir / source,
        min_interval_ms=NEWS_MIN_INTERVAL_MS[source],
    )
    items: list[dict[str, object]] = []
    extra = _supported(fetcher, {"safety_lag_ms": safety_lag_ms})
    try:
        for day_ms in days:
            items.extend(as_plain_dict(item) for item in fetcher(client=client, day_start_ms=day_ms, **extra))
    finally:
        _close(client)
    return items


def _fetch_comments(
    markets: Sequence[Mapping[str, object]],
    *,
    cache_dir: Path,
    safety_lag_ms: int,
) -> list[dict[str, object]]:
    """Every staged Manifold market's comments, numbered so two markets cannot collide on one id.

    A ``mfc`` news id is positional inside its day (section 2), so the day's next free index has to travel
    from one market to the next; the fetcher takes that map as ``index_offset_by_day``.
    """
    fetcher = cast(CommentFetcher, _resolve(*COMMENT_FETCHER_TARGET))
    client = _make_client(
        base_url=_importer_base_url("manifold"),
        cache_dir=cache_dir / "manifold_comment",
        min_interval_ms=NEWS_MIN_INTERVAL_MS["manifold_comment"],
    )
    items: list[dict[str, object]] = []
    offsets: dict[str, int] = {}
    try:
        for payload in markets:
            extra = _supported(
                fetcher,
                {"safety_lag_ms": safety_lag_ms, "index_offset_by_day": dict(offsets)},
            )
            market = _market_from_payload(payload)
            fetched = [as_plain_dict(item) for item in fetcher(client=client, market=market, **extra)]
            for item in fetched:
                key = day_key(_int_or_zero(item, "published_at_ms"))
                offsets[key] = offsets.get(key, 0) + 1
            items.extend(fetched)
    finally:
        _close(client)
    return items


def _asof_days(created_at_ms: int, resolved_at_ms: int) -> list[str]:
    """One day per ``ASOF_EVERY_DAYS`` of life, and none at or after the settling day (section 7.1)."""
    day_ms = (created_at_ms // MS_PER_DAY) * MS_PER_DAY
    last_ms = (resolved_at_ms // MS_PER_DAY) * MS_PER_DAY
    days: list[str] = []
    while day_ms < last_ms:
        days.append(iso_date_from_ms(day_ms))
        day_ms += ASOF_EVERY_DAYS * MS_PER_DAY
    return days


def _asof_titles(payload: Mapping[str, object]) -> list[str]:
    """A market's subjects in the order the background archive should snapshot them.

    Stated subjects first, derived ones only after them (section 7.2's ``wiki_subject_provenance``): a
    snapshot is one request per subject per week of market life, so the first subject is the one that
    gets snapshotted in practice, and a title the provider itself published is worth more than one this
    repository read off the question. A market file written before the flag existed carries no
    provenance and every subject reads as stated, which is the order it already had.
    """
    titles = payload.get("wiki_subjects")
    flags = payload.get("wiki_subject_provenance")
    if not isinstance(titles, list):
        return []
    subjects = [item for item in titles if isinstance(item, str)]
    provenance = [item for item in flags if isinstance(item, str)] if isinstance(flags, list) else []
    if len(provenance) != len(subjects):
        return subjects
    stated = [title for title, flag in zip(subjects, provenance, strict=True) if flag == SUBJECT_STATED]
    derived = [title for title, flag in zip(subjects, provenance, strict=True) if flag != SUBJECT_STATED]
    return stated + derived


def _fetch_asof(
    markets: Sequence[Mapping[str, object]],
    *,
    cache_dir: Path,
    safety_lag_ms: int,
    subjects: int,
) -> list[dict[str, object]]:
    fetcher = cast(AsofFetcher, _resolve(*ASOF_FETCHER_TARGET))
    client = _make_client(
        base_url=_news_base_url("wikipedia_asof"),
        cache_dir=cache_dir / "wikipedia_asof",
        min_interval_ms=NEWS_MIN_INTERVAL_MS["wikipedia_asof"],
    )
    extra = _supported(fetcher, {"safety_lag_ms": safety_lag_ms})
    items: list[dict[str, object]] = []
    try:
        for payload in markets:
            titles = _asof_titles(payload)
            if not titles:
                continue
            market_id = _str_or_empty(payload, "id")
            created = _int_or_zero(payload, "created_at_ms")
            resolved = _int_or_zero(payload, "resolved_at_ms")
            if not market_id or not created or not resolved:
                continue
            for title in titles[:subjects]:
                for asof_day in _asof_days(created, resolved):
                    items.extend(
                        as_plain_dict(item)
                        for item in fetcher(
                            client=client,
                            title=title,
                            asof_day=asof_day,
                            market_id=market_id,
                            **extra,
                        )
                    )
    finally:
        _close(client)
    return items


def _fetch_news(
    *,
    staging: Path,
    cache_dir: Path,
    freeze_date: str,
    window_days: int,
    sources: Sequence[str],
    safety_lag_ms: int,
    days_limit: int | None,
    asof_subjects: int,
    asof_providers: Sequence[str],
) -> int:
    window_start_ms, _window_end_ms, freeze_ms = _window(freeze_date, window_days)
    first_day_ms = (window_start_ms // MS_PER_DAY) * MS_PER_DAY
    last_day_ms = (freeze_ms // MS_PER_DAY) * MS_PER_DAY
    days = list(range(first_day_ms, last_day_ms, MS_PER_DAY))
    if days_limit is not None:
        days = days[-days_limit:]
    total = 0
    for source in sources:
        if source in DAY_FETCHER_TARGETS:
            items = _fetch_days(source, cache_dir=cache_dir, days=days, safety_lag_ms=safety_lag_ms)
        elif source == "manifold_comment":
            items = _fetch_comments(
                _staged_markets(staging, ("manifold",)),
                cache_dir=cache_dir,
                safety_lag_ms=safety_lag_ms,
            )
        elif source == "wikipedia_asof":
            items = _fetch_asof(
                _staged_markets(staging, asof_providers or ("kalshi",)),
                cache_dir=cache_dir,
                safety_lag_ms=safety_lag_ms,
                subjects=asof_subjects,
            )
        else:
            raise InvalidConfigError("unknown news source", source=source)
        stamped = sorted(_restamp_visibility(items, safety_lag_ms=safety_lag_ms), key=_news_sort_key)
        total += _write_jsonl(staging / NEWS_DIR / f"{source}.jsonl", stamped)
        print(f"staged {len(stamped)} {source} items to {staging / NEWS_DIR / f'{source}.jsonl'}")
    print(f"staged {total} news items over {len(days)} days")
    return total


def _cmd_news_fetch(args: argparse.Namespace) -> int:
    staging = Path(args.staging)
    _fetch_news(
        staging=staging,
        cache_dir=Path(args.cache_dir) if args.cache_dir else _default_cache(staging),
        freeze_date=cast(str, args.freeze),
        window_days=int(args.window_days),
        sources=_csv(args.source),
        safety_lag_ms=int(args.safety_lag_ms),
        days_limit=None if args.days is None else int(args.days),
        asof_subjects=int(args.asof_subjects),
        asof_providers=_csv(args.asof_providers),
    )
    return 0


# --------------------------------------------------------------------------------------------------
# build and refresh
# --------------------------------------------------------------------------------------------------
def _config_from_args(args: argparse.Namespace, providers: Sequence[str]) -> BuildConfig:
    return BuildConfig(
        freeze_date=cast(str, args.freeze),
        providers=tuple(sorted(set(providers))),
        interval_min=int(args.interval_min),
        window_days=int(args.window_days),
        opened_early_days=int(args.opened_early_days),
        min_trades=int(args.min_trades),
        min_unique_bettors=int(args.min_unique_bettors),
        min_life_days=int(args.min_life_days),
        min_traded_bars=int(args.min_traded_bars),
        min_traded_bars_per_day_permille=int(args.min_density_permille),
        exclude_self_resolved=not bool(args.keep_self_resolved),
        exclude_kalshi_shards=not bool(args.keep_kalshi_shards),
        safety_lag_ms=int(args.safety_lag_ms),
        news_sources=_csv(args.news_source) or ("wikipedia_current_events", "manifold_comment"),
        kalshi_series_allow_list=_csv(args.kalshi_series),
        limit_per_provider=args.limit_per_provider,
    )


def _excluded_series() -> tuple[str, ...]:
    """Kalshi's excluded series list, which section 7.4 keeps as data inside D2's importer.

    An absent importer means an empty list and not a failure: the ``KXMVE`` prefix rule of the same section
    is the builder's own, so a build without the series table still drops the shards the contract names.
    """
    try:
        module = importlib.import_module("pmx.data.importers.kalshi")
    except ImportError:  # pragma: no cover - D2 is a wave-1 sibling and lands before the gate
        return ()
    series = getattr(module, "KALSHI_EXCLUDED_SERIES", ())
    if isinstance(series, str) or not isinstance(series, Sequence):
        return ()
    return tuple(str(item) for item in series)


def _mapped_series() -> tuple[str, ...]:
    """The series a provider's series-to-category map names, for the builder's fallback count.

    Read off D2's importer for the same reason the excluded list is (and with the same tolerance for an
    absent importer): the builder counts how many kept markets fell back to the ``other`` category, and
    it can only do that if it knows which series were nameable at all.
    """
    try:
        module = importlib.import_module("pmx.data.importers.kalshi")
    except ImportError:  # pragma: no cover - D2 is a wave-1 sibling and lands before the gate
        return ()
    loader = getattr(module, "load_series_categories", None)
    if not callable(loader):
        return ()
    mapping = loader()
    if not isinstance(mapping, Mapping):
        return ()
    return tuple(str(series) for series in mapping)


def _run_build(
    *,
    out_dir: Path,
    config: BuildConfig,
    staging: Path,
    cache_dir: Path,
    offline: bool,
    seal: bool,
    notes: str,
    overwrite: bool,
    name: str | None,
    fetch_news: bool,
    min_interval_ms: int,
) -> int:
    if not offline:
        for provider in config.providers:
            _import_provider(
                provider,
                staging=staging,
                cache_dir=cache_dir,
                freeze_date=config.freeze_date,
                window_days=config.window_days,
                interval_min=config.interval_min,
                limit=config.limit_per_provider,
                min_interval_ms=min_interval_ms,
                series_allow_list=config.kalshi_series_allow_list,
                opened_early_days=config.opened_early_days,
                min_life_days=config.min_life_days,
            )
        if fetch_news:
            _fetch_news(
                staging=staging,
                cache_dir=cache_dir,
                freeze_date=config.freeze_date,
                window_days=config.window_days,
                sources=config.news_sources,
                safety_lag_ms=config.safety_lag_ms,
                days_limit=None,
                asof_subjects=1,
                asof_providers=(),
            )
    result: BuildResult = build_dataset_from_payloads(
        out_dir=out_dir,
        config=config,
        market_payloads=_staged_markets(staging, config.providers),
        news_payloads=_staged_news(staging),
        excluded_series=_excluded_series(),
        mapped_series=_mapped_series(),
        name=name,
        notes=notes,
        overwrite=overwrite,
    )
    manifest = result.manifest
    extra = [
        f"  dropped    {result.n_news_dropped} news items (source not selected, or older than every market)"
    ]
    # Ruling R101: a provider a build asked for and got nothing from is a result, not a silent zero. The
    # Manifold creator-resolved filter removes the whole provider by default, and a dataset that quietly
    # lost a provider reads exactly like one that never had it.
    empty = [name for name in config.providers if manifest.counts.per_provider.get(name, 0) == 0]
    for name in empty:
        extra.append(f"  WARNING    provider {name} contributed no market: every row it offered was filtered")
    if seal:
        sealer = cast(Callable[[Path], DatasetManifest], _resolve("pmx.data.loader", "seal_dataset"))
        manifest = sealer(out_dir)
    _print_manifest(manifest, out_dir, extra=extra)
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    providers = _csv(args.provider)
    if not providers:
        raise InvalidConfigError("build needs at least one --provider")
    config = _config_from_args(args, providers)
    out_dir = (
        Path(args.out)
        if args.out
        else DEFAULT_DATASETS / cast(str, args.name or DEFAULT_DATASET_NAME)
    )
    staging = Path(args.staging) if args.staging else out_dir / STAGING_DIR
    return _run_build(
        out_dir=out_dir,
        config=config,
        staging=staging,
        cache_dir=Path(args.cache_dir) if args.cache_dir else out_dir / CACHE_DIR,
        offline=bool(args.offline),
        seal=bool(args.seal),
        notes=cast(str, args.notes),
        overwrite=bool(args.force),
        name=cast("str | None", args.name),
        fetch_news=not bool(args.no_news),
        min_interval_ms=int(args.min_interval_ms),
    )


def _cmd_refresh(args: argparse.Namespace) -> int:
    """Slide the window forward into a **new** dataset, with the old one's filters and nothing else new."""
    source_dir = Path(args.dataset)
    out_dir = Path(args.out)
    if out_dir.resolve() == source_dir.resolve():
        raise InvalidConfigError(
            "a refresh writes a new dataset: an existing one is never edited in place",
            path=str(out_dir),
        )
    config = build_config_from_manifest(_load_manifest(source_dir), freeze_date=cast(str, args.freeze))
    staging = Path(args.staging) if args.staging else out_dir / STAGING_DIR
    return _run_build(
        out_dir=out_dir,
        config=config,
        staging=staging,
        cache_dir=Path(args.cache_dir) if args.cache_dir else out_dir / CACHE_DIR,
        offline=bool(args.offline),
        seal=bool(args.seal),
        notes=cast(str, args.notes),
        overwrite=bool(args.force),
        name=None,
        fetch_news=not bool(args.no_news),
        min_interval_ms=int(args.min_interval_ms),
    )


# --------------------------------------------------------------------------------------------------
# seal, verify, status, migrate-v1
# --------------------------------------------------------------------------------------------------
def _load_manifest(dataset_dir: Path) -> DatasetManifest:
    loader = cast(Callable[[Path], DatasetManifest], _resolve("pmx.data.loader", "load_manifest"))
    return loader(dataset_dir)


def _cmd_seal(args: argparse.Namespace) -> int:
    dataset_dir = Path(args.dataset)
    sealer = cast(Callable[[Path], DatasetManifest], _resolve("pmx.data.loader", "seal_dataset"))
    manifest = sealer(dataset_dir)
    print(f"sealed {manifest.name} {manifest.dataset_hash}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    """Recompute the hash and report; exit code 1 on any difference, which is what a gate reads."""
    dataset_dir = Path(args.dataset)
    reporter = cast(Callable[[Path], object], _resolve("pmx.data.loader", "verify_dataset_report"))
    report = reporter(dataset_dir)
    ok = bool(getattr(report, "ok", False))
    recomputed = cast(str, getattr(report, "dataset_hash", ""))
    expected = cast(str, getattr(report, "expected", ""))
    if ok:
        print(f"verified {dataset_dir} {recomputed}")
        return 0
    print(f"MISMATCH {dataset_dir}", file=sys.stderr)
    print(f"  recomputed {recomputed}", file=sys.stderr)
    print(f"  manifest   {expected}", file=sys.stderr)
    for label in ("mismatched_files", "missing_files", "extra_files"):
        names = cast(Sequence[str], getattr(report, label, ()))
        for name in names:
            print(f"  {label[:-6]:<11}{name}", file=sys.stderr)
    return 1


def _cmd_status(args: argparse.Namespace) -> int:
    dataset_dir = Path(args.dataset)
    manifest = _load_manifest(dataset_dir)
    if args.json:
        canonical = cast(Callable[[object], str], _resolve("pmx.journal", "canonical_json"))
        print(canonical(manifest.to_dict()))
        return 0
    extra = [f"  notes      {manifest.notes}"] if manifest.notes else []
    _print_manifest(manifest, dataset_dir, extra=extra)
    return 0


def _cmd_migrate_v1(args: argparse.Namespace) -> int:
    """Turn the twelve v1 markets into the v2 demo pack (D1's migration, section 7.10).

    There is no source path to give: the v1 markets are the bundled pack inside ``pmx.v1``, which is what
    makes the demo dataset reproducible from an installed wheel with no repository around it.
    """
    migrate = cast(Callable[..., object], _resolve("pmx.data.migrate_v1", "migrate_v1"))
    out_dir = Path(args.out)
    result = migrate(
        **_supported(
            migrate,
            {"out_dir": out_dir, "freeze_date": cast(str, args.freeze), "name": cast(str, args.name)},
        )
    )
    metas = getattr(result, "metas", ())
    print(f"migrated {len(metas) if isinstance(metas, Sequence) else 0} v1 markets to {out_dir}")
    manifest = _load_manifest(out_dir)
    _print_manifest(manifest, out_dir)
    return 0


def _csv(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.strip():
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


# --------------------------------------------------------------------------------------------------
# The parser
# --------------------------------------------------------------------------------------------------
def _add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--interval-min", type=int, default=1_440, choices=(60, 1_440))
    parser.add_argument("--window-days", type=int, default=365)
    parser.add_argument("--opened-early-days", type=int, default=90)
    parser.add_argument("--min-trades", type=int, default=50)
    parser.add_argument("--min-unique-bettors", type=int, default=30)
    parser.add_argument("--min-life-days", type=int, default=7)
    parser.add_argument(
        "--min-traded-bars",
        type=int,
        default=20,
        help="bars with size a bars-only market needs to pass min_trades (section 7.4)",
    )
    parser.add_argument("--min-density-permille", type=int, default=250)
    parser.add_argument("--keep-self-resolved", action="store_true", help="keep Manifold creator-resolved markets")
    parser.add_argument(
        "--kalshi-series",
        default="",
        help="comma separated Kalshi series tickers to ask the provider for (ruling R100)",
    )
    parser.add_argument("--keep-kalshi-shards", action="store_true", help="keep KXMVE style Kalshi shards")
    parser.add_argument("--safety-lag-ms", type=int, default=SAFETY_LAG_MS_DEFAULT)
    parser.add_argument("--news-source", default="", help="comma separated news sources to include")
    parser.add_argument("--limit-per-provider", type=int, default=None)


def _add_build_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--staging", default="", help="staged import directory (default <out>/staging)")
    parser.add_argument("--cache-dir", default="", help="raw provider cache (default <out>/cache)")
    parser.add_argument("--offline", action="store_true", help="build from staging only, open no socket")
    parser.add_argument("--no-news", action="store_true", help="skip the news fetch when not offline")
    parser.add_argument("--force", action="store_true", help="rebuild over an existing dataset directory")
    parser.add_argument("--notes", default="", help="free text stored in the manifest")
    parser.add_argument("--min-interval-ms", type=int, default=1_000)
    seal = parser.add_mutually_exclusive_group()
    seal.add_argument("--seal", dest="seal", action="store_true", default=True, help="seal after building")
    seal.add_argument("--no-seal", dest="seal", action="store_false", help="leave the dataset unsealed")


def build_parser(parser: argparse.ArgumentParser) -> None:
    """Mount the eight ``data`` subcommands on ``parser``."""
    sub = parser.add_subparsers(
        dest="data_command",
        metavar="{import,news,build,refresh,seal,verify,status,migrate-v1}",
    )

    p_import = sub.add_parser("import", help="import settled markets of one provider into staging")
    p_import.add_argument("provider", choices=sorted(IMPORTER_TARGETS))
    p_import.add_argument("--freeze", required=True, help="freeze date, yyyy-mm-dd")
    p_import.add_argument("--window-days", type=int, default=365)
    p_import.add_argument("--interval-min", type=int, default=1_440, choices=(60, 1_440))
    p_import.add_argument("--staging", default=str(_default_staging(DEFAULT_DATASET_NAME)))
    p_import.add_argument("--cache-dir", default="", help="raw provider cache (default beside staging)")
    p_import.add_argument("--limit", type=int, default=None)
    p_import.add_argument(
        "--opened-early-days",
        type=int,
        default=90,
        help="how far before the window a market may have opened (section 7.4); bounds a walk by creation",
    )
    p_import.add_argument("--min-interval-ms", type=int, default=1_000)
    p_import.add_argument(
        "--min-life-days",
        type=int,
        default=0,
        help="life a row must have for its tape to be worth fetching (the min_life filter of 7.4)",
    )
    p_import.add_argument(
        "--kalshi-series", default="", help="comma separated Kalshi series tickers (ruling R100)"
    )
    p_import.set_defaults(func=_cmd_import)

    p_news = sub.add_parser("news", help="fetch the dated news archive into staging")
    news_sub = p_news.add_subparsers(dest="news_command", metavar="{fetch}")
    p_fetch = news_sub.add_parser("fetch", help="fetch each news source over the window, one day at a time")
    p_fetch.add_argument("--freeze", required=True, help="freeze date, yyyy-mm-dd")
    p_fetch.add_argument("--window-days", type=int, default=365)
    p_fetch.add_argument("--source", default="wikipedia_current_events", help="comma separated sources")
    p_fetch.add_argument("--staging", default=str(_default_staging(DEFAULT_DATASET_NAME)))
    p_fetch.add_argument("--cache-dir", default="", help="raw provider cache (default beside staging)")
    p_fetch.add_argument("--days", type=int, default=None, help="fetch only the last N days of the window")
    p_fetch.add_argument("--safety-lag-ms", type=int, default=SAFETY_LAG_MS_DEFAULT)
    p_fetch.add_argument("--asof-subjects", type=int, default=1)
    p_fetch.add_argument("--asof-providers", default="", help="providers whose markets get background snapshots")
    p_fetch.set_defaults(func=_cmd_news_fetch)

    p_build = sub.add_parser("build", help="filter, tag, split, write and hash a dataset")
    p_build.add_argument("--provider", required=True, help="comma separated providers")
    p_build.add_argument("--freeze", required=True, help="freeze date, yyyy-mm-dd")
    p_build.add_argument("--out", default="", help="dataset directory (default data/datasets/<name>)")
    p_build.add_argument("--name", default=None, help="dataset name (default the output directory's name)")
    _add_filter_arguments(p_build)
    _add_build_arguments(p_build)
    p_build.set_defaults(func=_cmd_build)

    p_refresh = sub.add_parser("refresh", help="slide the window forward into a new dataset")
    p_refresh.add_argument("--dataset", required=True, help="the dataset whose filters are reused")
    p_refresh.add_argument("--freeze", required=True, help="the new freeze date, yyyy-mm-dd")
    p_refresh.add_argument("--out", required=True, help="the new dataset directory")
    _add_build_arguments(p_refresh)
    p_refresh.set_defaults(func=_cmd_refresh)

    p_seal = sub.add_parser("seal", help="recompute the hash and mark the dataset immutable")
    p_seal.add_argument("--dataset", required=True)
    p_seal.set_defaults(func=_cmd_seal)

    p_verify = sub.add_parser("verify", help="recompute the hash and refuse any difference")
    p_verify.add_argument("--dataset", required=True)
    p_verify.set_defaults(func=_cmd_verify)

    p_status = sub.add_parser("status", help="print a dataset's window, counts, filters and split")
    p_status.add_argument("--dataset", required=True)
    p_status.add_argument("--json", action="store_true", help="print the manifest as canonical JSON")
    p_status.set_defaults(func=_cmd_status)

    p_migrate = sub.add_parser("migrate-v1", help="turn the twelve bundled v1 markets into the v2 demo pack")
    p_migrate.add_argument("--out", default=str(DEFAULT_DEMO_OUT))
    p_migrate.add_argument("--name", default="demo_v1", help="dataset name stamped in the demo manifest")
    p_migrate.add_argument("--freeze", default="2026-09-07", help="freeze date stamped in the demo manifest")
    p_migrate.set_defaults(func=_cmd_migrate_v1)


def _dispatch_group(args: argparse.Namespace) -> int:
    """What ``pmx data`` alone does: nothing, loudly."""
    print("pmx data needs a subcommand: import, news, build, refresh, seal, verify, status, migrate-v1")
    return 2


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Mount ``pmx data`` on the top level parser (U4 calls this in wave 5)."""
    parser = subparsers.add_parser("data", help="import, build, seal and inspect datasets")
    build_parser(parser)
    parser.set_defaults(func=_dispatch_group)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the group as a program, which is how it is driven before U4 wires it into ``pmx``."""
    parser = argparse.ArgumentParser(
        prog="pmx data",
        description="Import, build, seal and inspect the datasets a run is judged against.",
    )
    build_parser(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return cast(Callable[[argparse.Namespace], int], handler)(args)
    except PmxError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised through a subprocess in the tests
    raise SystemExit(main())
