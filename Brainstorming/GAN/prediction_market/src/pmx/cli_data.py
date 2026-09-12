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
import dataclasses
import importlib
import inspect
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from pmx.cohorts import COHORT_MIN_TRAIN
from pmx.data.builder import (
    FALLBACK_STEPS,
    FOLD_NAMES,
    PURPOSE_RESEARCH,
    PURPOSES,
    UNIVERSE_MIN_SETTLED_DEFAULT,
    UNIVERSE_MIN_VOLUME_CENTS_DEFAULT,
    WINDOW_DAYS_MAX,
    BuildResult,
    as_plain_dict,
    build_config_from_manifest,
    build_dataset_from_payloads,
    check_purpose,
    check_window_days,
)
from pmx.data.news.linker import (
    AUDIT_HASH_PREFIX,
    AUDITS_DIR,
    LINKER_AUDIT_FILE,
    LINKER_AUDIT_N,
    LINKER_PRECISION_MIN_PERMILLE,
    LinkerAudit,
    all_links_of,
    audit_from_dict,
    linker_audit_path,
    sample_audit_links,
)
from pmx.data.taxonomy import (
    TAXONOMY_AUDIT_N,
    TAXONOMY_COVERAGE_MIN_PERMILLE,
    TaggedMarket,
    TaxonomyAudit,
    sample_taxonomy_audit,
    taxonomy_audit_from_dict,
    taxonomy_audit_manifest_path,
    taxonomy_audit_path,
    weak_venues,
)
from pmx.data.universe import UniverseRule, render_series_list
from pmx.errors import InvalidConfigError, NotConfiguredError, PmxError
from pmx.types import (
    INTERVALS_MIN,
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

#: The repository root, which is where the **tracked** ``audits/`` tree of 7.1 lives (ruling R296): it
#: is outside every dataset directory and every dataset hash, and it is not under the git-ignored
#: ``data/datasets/``, because git cannot re-include a file under an excluded directory.
AUDITS_ROOT = Path()

DEFAULT_DATASETS = Path("data/datasets")
DEFAULT_DEMO_OUT = Path("data/demo_v1")
DEFAULT_DATASET_NAME = "default"

#: Staging and the HTTP cache both live inside the dataset directory: section 7.11 puts the cache at
#: ``data/datasets/<name>/cache/``, and neither belongs in the dataset hash (section 4.3 walks
#: ``markets/``, ``news/`` and ``wiki_asof/`` and nothing else), so the git-ignored ``data/datasets/*``
#: already covers both and no new ignore rule is needed for a year of raw provider answers.
STAGING_DIR = "staging"

#: The Kalshi series list a build produces (7.4, ruling R258): an output, one ticker per line, at the
#: dataset root and outside the four hashed directories of 4.3.
SERIES_LIST_FILE = "kalshi_series.txt"

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
    # Decision D-S3, ruling R262: the ceiling is refused at the flag as well as inside the build, so
    # ``pmx data build --window-days 900`` fails before it opens a socket rather than after the walk.
    check_window_days(int(args.window_days))
    check_purpose(str(getattr(args, "purpose", PURPOSE_RESEARCH)))
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


def _series_categories() -> dict[str, str]:
    """D2's sealed series-to-category map (ruling R170), read for the weather label of 7.4.

    Read off the importer for the reason ``_excluded_series`` is, and with the same tolerance for an
    absent one: the universe rule keeps a weather series and labels it
    ``forecastable_from_public_models``, and it can only know which series those are from the map.
    """
    try:
        module = importlib.import_module("pmx.data.importers.kalshi")
    except ImportError:  # pragma: no cover - D2 is a wave-1 sibling and lands before the gate
        return {}
    loader = getattr(module, "load_series_categories", None)
    if not callable(loader):
        return {}
    mapping = loader()
    if not isinstance(mapping, Mapping):
        return {}
    return {str(series): str(category) for series, category in mapping.items()}


def _write_linker_audit(dataset_dir: Path, *, root: Path, n: int = LINKER_AUDIT_N) -> LinkerAudit:
    """Draw ``n`` links of a sealed dataset and write ``audits/<hash[:16]>/linker.json`` (7.6, R250).

    Two rules of the file are worth stating where it is written. It is drawn **after** the seal and is
    keyed by the hash it audits, because a link the reviewer read must be a link the dataset still
    carries. And it lives in the **tracked** ``audits/`` tree and never under the git-ignored
    ``data/datasets/`` (ruling R296): fifty human verdicts cannot be regenerated, and git cannot
    re-include a file under an excluded directory.

    Re-running over a file whose verdicts are filled keeps every verdict, because the draw is a pure
    function of the dataset hash: the same dataset always offers the same fifty links.
    """
    load_dataset = cast(Callable[..., object], _resolve("pmx.data.loader", "load_dataset"))
    dataset = load_dataset(dataset_dir)
    manifest = cast(DatasetManifest, getattr(dataset, "manifest", None))  # noqa: B009
    news_loader = getattr(dataset, "news_global", None)
    items = news_loader(1 << 62) if callable(news_loader) else ()
    sample_seed = cast(Callable[[str], int], _resolve("pmx.data.builder", "sample_seed_for"))(manifest.name)
    drawn = sample_audit_links(all_links_of(items), sample_seed=sample_seed, n=n)
    path = linker_audit_path(root, manifest.dataset_hash)
    previous: dict[tuple[str, str], tuple[str | None, str]] = {}
    if path.is_file():
        for link in audit_from_dict(json.loads(path.read_text(encoding="utf-8"))).links:
            previous[(link.news_id, link.market_id)] = (link.verdict, link.reviewer)
    kept = tuple(
        dataclasses.replace(
            link,
            verdict=previous.get((link.news_id, link.market_id), (None, ""))[0],
            reviewer=previous.get((link.news_id, link.market_id), (None, ""))[1],
        )
        for link in drawn
    )
    audit = LinkerAudit(
        dataset_hash=manifest.dataset_hash, sample_seed=sample_seed, n=len(kept), links=kept
    )
    writer = cast(Callable[[Path, object], int], _resolve("pmx.data.loader", "write_canonical_json"))
    writer(path, audit.to_dict())
    return audit


def _write_taxonomy_audit(
    dataset_dir: Path,
    *,
    root: Path,
    rows: Sequence[TaggedMarket],
    questions: Mapping[str, str],
    dataset_hash: str,
    name: str,
    n: int = TAXONOMY_AUDIT_N,
) -> TaxonomyAudit:
    """Draw ``n`` taggings of a sealed build and write ``audits/<hash[:16]>/taxonomy.json`` (7.14, R268).

    The same two rules as the linker's audit beside it (:func:`_write_linker_audit`): it is drawn
    **after** the seal and keyed by the hash it audits, because a tagging the reviewer read must be a
    tagging the dataset still carries, and it lives in the **tracked** ``audits/`` tree and never under
    the git-ignored ``data/datasets/`` (ruling R296), because fifty human verdicts cannot be regenerated.

    ``rows`` is the ``TaggedMarket`` list the build already assembled and is not re-derived from the
    market files: the facet ``source`` a reviewer needs (``series``, ``keywords`` or ``other``) is what
    the tagger decided and a market file does not store it. Re-running keeps every verdict already
    filled, because the draw is a pure function of the dataset hash.
    """
    sample_seed = cast(Callable[[str], int], _resolve("pmx.data.builder", "sample_seed_for"))(name)
    audit = sample_taxonomy_audit(
        rows, questions, dataset_hash=dataset_hash, sample_seed=sample_seed, n=n
    )
    path = taxonomy_audit_path(root, dataset_hash)
    audit = _merge_taxonomy_verdicts(audit, path)
    writer = cast(Callable[[Path, object], int], _resolve("pmx.data.loader", "write_canonical_json"))
    writer(path, audit.to_dict())
    return audit


def _merge_taxonomy_verdicts(audit: TaxonomyAudit, path: Path) -> TaxonomyAudit:
    """Carry the verdicts of an existing audit file onto a freshly drawn one, per market and per facet.

    Without this a second ``pmx data build`` over the same bytes would overwrite a reviewer's work with
    fifty nulls. The draw is deterministic in the dataset hash, so the fifty are the same fifty and the
    merge is a lookup by market id.
    """
    if not path.is_file():
        return audit
    previous = {
        row.market_id: row.verdicts
        for row in taxonomy_audit_from_dict(json.loads(path.read_text(encoding="utf-8"))).taggings
    }
    return dataclasses.replace(
        audit,
        taggings=tuple(
            dataclasses.replace(row, verdicts=dict(previous[row.market_id]))
            if row.market_id in previous
            else row
            for row in audit.taggings
        ),
    )


def _stamp_taxonomy_audit(
    out_dir: Path, manifest: DatasetManifest, audit: TaxonomyAudit
) -> DatasetManifest:
    """Write ``taxonomy.audit {path, n, precision_permille}`` into the sealed manifest (7.8, R268).

    The manifest is outside ``dataset_hash`` (4.3 hashes the directories, not the document that names
    their digest), so stamping it after the seal moves no hash, exactly as ``news.linker_audit`` does.
    ``precision_permille`` is ``0`` until a reviewer fills the verdicts, which is the point: a build
    whose taggings nobody has looked at is not a build whose taggings are good, and gate G3 is the review.
    """
    if manifest.taxonomy is None:
        raise InvalidConfigError(
            "a dataset with no taxonomy block cannot carry a taxonomy audit", path=str(out_dir)
        )
    stamped = dataclasses.replace(
        manifest,
        taxonomy={
            **dict(manifest.taxonomy),
            "audit": audit.manifest_block(taxonomy_audit_manifest_path(manifest.dataset_hash)),
        },
    )
    writer = cast(Callable[[Path, DatasetManifest], int], _resolve("pmx.data.loader", "write_manifest"))
    writer(out_dir, stamped)
    return stamped


def _taxonomy_audit_lines(audit: TaxonomyAudit, manifest: DatasetManifest, path: Path) -> list[str]:
    """The three lines a build log prints about the tagging audit, beside the linker's two."""
    weak = weak_venues(manifest.taxonomy or {})
    lines = [
        f"  taxonomy   {audit.n} taggings drawn for review at {path}",
        f"  tag prec   {audit.precision_permille} permille"
        + (f"  taxonomy: weak on {list(weak)}" if weak else ""),
    ]
    per_venue = (manifest.taxonomy or {}).get("per_venue")
    if isinstance(per_venue, Mapping):
        for provider in sorted(per_venue):
            row = per_venue[provider]
            if isinstance(row, Mapping):
                lines.append(
                    f"  facets     {provider}: subject {row.get('subject_coverage_permille')}"
                    f" structure {row.get('structure_coverage_permille')} permille"
                    f" (bar {TAXONOMY_COVERAGE_MIN_PERMILLE}),"
                    f" cohorts {row.get('n_cohorts')} of which {row.get('n_cohorts_usable')} usable,"
                    f" label {row.get('label')}"
                )
    return lines


def _cmd_audit_taxonomy(args: argparse.Namespace) -> int:
    """``pmx data audit-taxonomy``: recompute the tagging audit's precision and re-stamp the manifest.

    The file itself is written by the build that drew it, because only the build holds the facet
    ``source`` of each tagging. This command is the other half of the loop the linker already has: once a
    reviewer has filled the verdicts, the manifest's ``taxonomy.audit.precision_permille`` has to move,
    or a reviewed build reads ``taxonomy: weak`` forever.
    """
    dataset_dir = Path(args.dataset)
    reader = cast(Callable[[Path], DatasetManifest], _resolve("pmx.data.loader", "load_manifest"))
    manifest = reader(dataset_dir)
    path = taxonomy_audit_path(Path(args.audits_root), manifest.dataset_hash)
    if not path.is_file():
        raise InvalidConfigError(
            "no tagging audit was drawn for this dataset hash; the build that seals it draws one",
            path=str(path),
        )
    audit = taxonomy_audit_from_dict(json.loads(path.read_text(encoding="utf-8")))
    manifest = _stamp_taxonomy_audit(dataset_dir, manifest, audit)
    print(f"taxonomy audit {path}")
    print(f"  taggings   {audit.n} drawn, {audit.n_reviewed} reviewed")
    print(f"  verdicts   correct {audit.n_correct}  wrong {audit.n_wrong}")
    print(f"  precision  {audit.precision_permille} permille")
    for line in _taxonomy_audit_lines(audit, manifest, path)[2:]:
        print(line)
    return 0


def _cmd_audit_links(args: argparse.Namespace) -> int:
    """``pmx data audit-links``: write the fifty-link audit file, or recompute its precision (D-R4)."""
    dataset_dir = Path(args.dataset)
    audit = _write_linker_audit(dataset_dir, root=Path(args.audits_root), n=int(args.n))
    path = linker_audit_path(Path(args.audits_root), audit.dataset_hash)
    # The manifest's ``news.linker_audit`` carries the precision, so a review that fills the verdicts
    # has to move it: a leaderboard row reads ``news_links: weak`` off the dataset (7.6, 12.10) and a
    # reviewed build whose manifest still said zero would be labelled weak forever.
    reader = cast(Callable[[Path], DatasetManifest], _resolve("pmx.data.loader", "load_manifest"))
    _stamp_linker_audit(dataset_dir, reader(dataset_dir), audit)
    print(f"linker audit {path}")
    print(f"  links      {audit.n} drawn, {audit.n_reviewed} reviewed")
    print(f"  verdicts   correct {audit.n_correct}  wrong {audit.n_wrong}")
    print(f"  precision  {audit.precision_permille} permille (bar {LINKER_PRECISION_MIN_PERMILLE})")
    if audit.weak:
        print("  label      news_links: weak")
    return 0


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
    purpose: str = PURPOSE_RESEARCH,
    universe_rule: UniverseRule | None = None,
    audits_root: Path | None = None,
    fallbacks: Sequence[Mapping[str, object]] = (),
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
        series_categories=_series_categories(),
        purpose=purpose,
        universe_rule=universe_rule,
        fallbacks=fallbacks,
        name=name,
        notes=notes,
        overwrite=overwrite,
    )
    manifest = result.manifest
    extra = [
        f"  dropped    {result.n_news_dropped} news items (source not selected, or older than every market)"
    ]
    extra.extend(_build_report(result))
    universe = result.universe
    if universe is not None and universe.n_series_after:
        # The series list is an **output** of the build (7.4, ruling R258), written one ticker per line:
        # the file the first build shipped was one comma-separated line and a reader that split on
        # newlines silently got zero series (docs/MEASURE_2026-09-09_KALSHI_UNIVERSE.md section 4.2).
        # It sits at the dataset root, outside the four hashed directories of 4.3, because it is a
        # convenience for the next build and the evidence is the manifest block.
        series_path = out_dir / SERIES_LIST_FILE
        series_path.write_text(
            render_series_list(universe.series_tickers), encoding="utf-8", newline="\n"
        )
        extra.append(f"  series     {universe.n_series_after} tickers written to {series_path}")
    # Ruling R101: a provider a build asked for and got nothing from is a result, not a silent zero. The
    # Manifold creator-resolved filter removes the whole provider by default, and a dataset that quietly
    # lost a provider reads exactly like one that never had it.
    empty = [name for name in config.providers if manifest.counts.per_provider.get(name, 0) == 0]
    for name in empty:
        extra.append(f"  WARNING    provider {name} contributed no market: every row it offered was filtered")
    if seal:
        sealer = cast(Callable[[Path], DatasetManifest], _resolve("pmx.data.loader", "seal_dataset"))
        manifest = sealer(out_dir)
        # The audit is drawn after the seal and keyed by the hash it audits (7.6, ruling R250), so it is
        # written here and never inside the builder, whose hash is still moving when it returns. The
        # manifest then gains ``news.linker_audit`` (7.8): the manifest is outside ``dataset_hash``
        # (4.3 hashes the directories and not the document that names their digest), so stamping it
        # after the seal moves no hash and the label a leaderboard row reads is on the dataset itself
        # rather than in a file beside it.
        root = audits_root if audits_root is not None else AUDITS_ROOT
        audit = _write_linker_audit(out_dir, root=root)
        path = linker_audit_path(root, manifest.dataset_hash)
        manifest = _stamp_linker_audit(out_dir, manifest, audit)
        extra.append(f"  audit      {audit.n} links drawn for review at {path}")
        extra.append(
            f"  precision  {audit.precision_permille} permille"
            + ("  news_links: weak" if audit.weak else "")
        )
        # The fifty-tagging audit of 7.14, drawn beside the linker's and into the same tracked tree
        # (ruling R296). Both are keyed by the hash they audit and both stamp a manifest block outside
        # the hash, so a reviewer's verdicts move a label and never a dataset.
        tag_audit = _write_taxonomy_audit(
            out_dir,
            root=root,
            rows=result.tagged,
            questions=result.questions,
            dataset_hash=manifest.dataset_hash,
            name=manifest.name,
        )
        tag_path = taxonomy_audit_path(root, manifest.dataset_hash)
        manifest = _stamp_taxonomy_audit(out_dir, manifest, tag_audit)
        extra.extend(_taxonomy_audit_lines(tag_audit, manifest, tag_path))
    _print_manifest(manifest, out_dir, extra=extra)
    return 0


def _stamp_linker_audit(
    out_dir: Path, manifest: DatasetManifest, audit: LinkerAudit
) -> DatasetManifest:
    """Write ``news.linker_audit {path, n, precision_permille}`` into the sealed manifest (7.8, R250).

    The path is the tracked ``audits/<dataset_hash[:16]>/linker.json`` of ruling R296, relative to the
    audits root, which is the shape ``dataset.v1.json`` pins: an absolute path would be a statement
    about one machine. ``precision_permille`` is ``0`` until a reviewer fills the verdicts, which is
    deliberate (7.6): a build whose links nobody has looked at is not a build whose links are good.
    """
    stamped = dataclasses.replace(
        manifest,
        news=dataclasses.replace(
            manifest.news,
            linker_audit=audit.manifest_block(
                f"{AUDITS_DIR}/{manifest.dataset_hash[:AUDIT_HASH_PREFIX]}/{LINKER_AUDIT_FILE}"
            ),
        ),
    )
    writer = cast(Callable[[Path, DatasetManifest], int], _resolve("pmx.data.loader", "write_manifest"))
    writer(out_dir, stamped)
    return stamped


def _build_report(result: BuildResult) -> list[str]:
    """The answers amendment C1c added to a build, printed beside the manifest that now carries them.

    ``purpose``, ``window_days``, the ``split`` cuts and moves, ``universe``, ``resolution_span`` and
    ``build`` are manifest blocks in 7.8 and the builder writes every one of them since 18.8's first
    two rows landed in ``pmx.types`` and ``pmx.data.schema``. They are still printed, because an
    operator reading a build log should not have to open the document to see what the cut did, and
    ``BuildResult.manifest_blocks`` is that document.
    """
    lines = [f"  purpose    {result.purpose}"]
    plan = result.plan
    if plan is not None:
        lines.append(
            f"  cuts       train_end {day_key(plan.train_end_ms)}"
            f"  validation_end {day_key(plan.validation_end_ms)}"
            f"  method count_quantile {list(plan.quantiles_permille)}"
        )
        lines.append(
            f"  realised   {list(plan.realised_permille)} permille"
            f"  moved {len(plan.cluster_moves)}"
            + (f"  EMPTY FOLDS {list(plan.empty_folds)}" if plan.empty_folds else "")
        )
    universe = result.universe
    if universe is not None and universe.n_series_before:
        lines.append(
            f"  universe   {universe.n_series_after} of {universe.n_series_before} series pass"
            f" (>= {universe.rule.min_settled} settled, >= {universe.rule.min_volume_cents} cents),"
            f" {universe.n_markets_kept} markets kept in them"
        )
    outcome = result.outcome
    if outcome:
        lines.append(f"  build      status {outcome.get('status')}  shortfall {outcome.get('shortfall')}")
        steps = outcome.get("fallbacks")
        if isinstance(steps, list) and steps:
            for step in steps:
                lines.append(f"  fallback   {step}")
    taxonomy = result.manifest.taxonomy
    if isinstance(taxonomy, Mapping):
        lines.append(
            f"  cohorts    {len(result.cohorts)} listed,"
            f" {sum(1 for cohort in result.cohorts if cohort.usable)} usable at {COHORT_MIN_TRAIN}"
            f" train markets, sizes {taxonomy.get('cohort_size_histogram')}"
        )
    return lines


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
        purpose=cast(str, args.purpose),
        universe_rule=_universe_rule_from_args(args),
        audits_root=Path(args.audits_root),
        fallbacks=_fallbacks_from_args(args),
    )


def _universe_rule_from_args(args: argparse.Namespace) -> UniverseRule:
    """The two bars of the documented universe rule (7.4, decision D-R13, ruling R258)."""
    return UniverseRule(
        min_settled=int(args.universe_min_settled),
        min_volume_cents=int(args.universe_min_volume_cents),
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
    check_window_days(config.window_days)
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
        purpose=cast(str, args.purpose),
        universe_rule=_universe_rule_from_args(args),
        audits_root=Path(args.audits_root),
        fallbacks=_fallbacks_from_args(args),
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
        # 7.8, ruling R248: ``pmx data verify`` also checks that no cluster or ``event_key`` group spans
        # two folds and that the manifest's three counts are what the group-aware cut recomputes. The
        # hash says the bytes are the ones the manifest names; this says the folds they fall into are
        # the count-quantile, cluster-aware folds of 7.7 and not the calendar thirds that gave the first
        # real dataset an inverted pyramid.
        folds = cast(Callable[[Path], Mapping[str, str]], _resolve("pmx.data.loader", "verify_folds"))
        try:
            assignment = folds(dataset_dir)
        except PmxError as error:
            print(f"FOLD INTEGRITY {dataset_dir}", file=sys.stderr)
            print(f"  {error}", file=sys.stderr)
            return 1
        counted = {name: sum(1 for fold in assignment.values() if fold == name) for name in FOLD_NAMES}
        print(f"verified {dataset_dir} {recomputed}")
        print(f"  folds      {' '.join(f'{name} {counted[name]}' for name in FOLD_NAMES)}")
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
    """A comma separated flag, split on newlines as well.

    The newline is the measurement's correction of 7.4 applied to the flag (ruling R258,
    ``docs/MEASURE_2026-09-09_KALSHI_UNIVERSE.md`` section 4.2): a build writes its series list one
    ticker per line, so ``--kalshi-series "$(cat data/datasets/y2026/kalshi_series.txt)"`` has to mean
    seven hundred tickers and not one seven-thousand-character ticker the exchange has never heard of.
    """
    if not isinstance(value, str) or not value.strip():
        return ()
    flattened = value.replace("\r", ",").replace("\n", ",")
    return tuple(part.strip() for part in flattened.split(",") if part.strip())


# --------------------------------------------------------------------------------------------------
# The parser
# --------------------------------------------------------------------------------------------------
def _add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--interval-min",
        type=int,
        default=1_440,
        choices=(60, 1_440),
        help=(
            "the dataset's one bar grid (5.2, 5.3). 60 is the headline Kalshi grid (decision D-R5): "
            "Kalshi publishes 1-minute candlesticks and a daily grid discards its intraday content "
            "while the latency rule costs a full day. 1440 stays for Manifold and the showcase pack"
        ),
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=365,
        help=(
            f"the window on resolved_at_ms (5.6, decision D-S3); refused above {WINDOW_DAYS_MAX} "
            "because an older resolution is recall rather than forecast for an LLM and an older "
            "regime is not the regime being traded"
        ),
    )
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


def _fallbacks_from_args(args: argparse.Namespace) -> tuple[Mapping[str, object], ...]:
    """``manifest.build.fallbacks`` from the repeated ``--fallback`` flag (7.4, ruling R271).

    R271 asks the builder to record the fallback order it took, and ``build_outcome(fallbacks=...)`` has
    been reachable from Python alone since it landed, so the list was empty on every real build: an
    operator who widened the window to reach the cohort target had no way to say so. The four fields of
    7.8's row are positional and split on the **first three** colons, because a reason is prose and
    contains them.
    """
    rows: list[Mapping[str, object]] = []
    for raw in cast("list[str]", getattr(args, "fallback", []) or []):
        parts = raw.split(":", 3)
        if len(parts) != 4 or not all(part.strip() for part in parts):
            raise InvalidConfigError(
                "a fallback step is step:from:to:reason (7.8, ruling R271)", fallback=raw
            )
        step, moved_from, moved_to, reason = (part.strip() for part in parts)
        if step not in FALLBACK_STEPS:
            raise InvalidConfigError(
                "a fallback names one of the four steps of 7.8",
                step=step,
                steps=list(FALLBACK_STEPS),
            )
        if not (moved_from.lstrip("-").isdigit() and moved_to.lstrip("-").isdigit()):
            raise InvalidConfigError(
                "a fallback moves a step from one integer to another (7.8: both are integers)",
                fallback=raw,
            )
        rows.append(
            {"step": step, "from": int(moved_from), "to": int(moved_to), "reason": reason}
        )
    return tuple(rows)


def _add_build_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--purpose",
        default=PURPOSE_RESEARCH,
        choices=PURPOSES,
        help=(
            "research obeys the window rule of 5.6; showcase holds landmark events kept apart, is "
            "exempt from the window rule and from nothing else, and is never the source of a fold, a "
            "fitness value, a rule promotion or a claim (decision D-S4)"
        ),
    )
    parser.add_argument(
        "--universe-min-settled",
        type=int,
        default=UNIVERSE_MIN_SETTLED_DEFAULT,
        help="settled markets in the window a Kalshi series needs to enter the universe (7.4, D-R13)",
    )
    parser.add_argument(
        "--universe-min-volume-cents",
        type=int,
        default=UNIVERSE_MIN_VOLUME_CENTS_DEFAULT,
        help="volume in cents a Kalshi series needs to enter the universe (7.4, D-R13)",
    )
    parser.add_argument(
        "--audits-root",
        default=str(AUDITS_ROOT),
        help="root of the tracked audits/ tree the linker audit is written into (7.1, ruling R296)",
    )
    parser.add_argument(
        "--fallback",
        action="append",
        default=[],
        metavar="STEP:FROM:TO:REASON",
        help=(
            "one step of the fallback order this build took, repeatable and recorded in "
            "manifest.build.fallbacks in the order given (7.4, ruling R271); for example "
            "window_days:365:540:cohort target unreachable at 365"
        ),
    )
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
    """Mount the ten ``data`` subcommands on ``parser``.

    The metavar is spelled out rather than left to argparse because it is what an error message shows,
    and it had gone stale: ``audit-links`` was missing from it, and ``audit-taxonomy`` joins it here.
    """
    sub = parser.add_subparsers(
        dest="data_command",
        metavar=(
            "{import,news,build,refresh,seal,verify,audit-links,audit-taxonomy,status,migrate-v1}"
        ),
    )

    p_import = sub.add_parser("import", help="import settled markets of one provider into staging")
    p_import.add_argument("provider", choices=sorted(IMPORTER_TARGETS))
    p_import.add_argument("--freeze", required=True, help="freeze date, yyyy-mm-dd")
    p_import.add_argument("--window-days", type=int, default=365)
    # Every grid of ``INTERVALS_MIN`` (5.2), the minute one included: 18.3 and ruling R298 put the
    # refusal of a minute build on ``BuildConfig.__post_init__`` (a coarse source, or neither an
    # instrument list nor a series list), so a flag that offered only the two coarse grids refused a
    # staging import the build itself would have judged on its own terms.
    p_import.add_argument(
        "--interval-min",
        type=int,
        default=1_440,
        choices=INTERVALS_MIN,
        help="the bar grid of the import, one of INTERVALS_MIN (5.2, 18.3)",
    )
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

    p_audit = sub.add_parser(
        "audit-links",
        help="draw the fifty-link precision audit of a sealed dataset, or recompute its precision",
    )
    p_audit.add_argument("--dataset", required=True)
    p_audit.add_argument(
        "--audits-root",
        default=str(AUDITS_ROOT),
        help="root of the tracked audits/ tree (7.1, ruling R296)",
    )
    p_audit.add_argument("--n", type=int, default=LINKER_AUDIT_N, help="how many links to draw (7.6)")
    p_audit.set_defaults(func=_cmd_audit_links)

    p_tags = sub.add_parser(
        "audit-taxonomy",
        help="recompute the fifty-tagging audit's precision and re-stamp manifest.taxonomy.audit",
    )
    p_tags.add_argument("--dataset", required=True)
    p_tags.add_argument(
        "--audits-root",
        default=str(AUDITS_ROOT),
        help="root of the tracked audits/ tree (7.1, ruling R296)",
    )
    p_tags.set_defaults(func=_cmd_audit_taxonomy)

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
    print(
        "pmx data needs a subcommand: import, news, build, refresh, seal, verify, audit-links, "
        "status, migrate-v1"
    )
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
