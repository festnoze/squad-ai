"""Reading a dataset directory, and the two operations that make one trustworthy: seal and verify.

A dataset is evidence. Everything downstream (a score, a claim, a leaderboard row) is a statement about
these bytes, so this module refuses a dataset that is not exactly what its manifest says it is, and it
refuses it **before** a run starts rather than after a number has been produced (CONTRACTS_V2 sections
7.1, 7.2, 7.3, 7.8 and 7.9).

Three families of check live here, and none of them can be expressed by a JSON schema:

* **Structure.** Bars dense on the one grid of the dataset, no gap and no duplicate, from
  ``bar_of(created_at_ms)`` to ``bar_of(resolved_at_ms)``; trades in the canonical order; a bar's low at
  or under its open, close and vwap, and its high at or over them; ``final_price_bp`` equal to the close
  of the last bar. A gap would make ``bar_at`` return ``None`` mid-run and an ordering would make a fill
  depend on the order a file happened to be written in.
* **As-of.** ``visible_from_ms == published_at_ms + safety_lag_ms`` recomputed from the manifest, the news
  day key equal to ``day_start_ms(published_at_ms)``, and a background snapshot refused when its revision
  is newer than the day it claims. That last one is the signature of the highest-value leak in the design:
  today's article on "will X win", which states the outcome, stamped with an early date.
* **Integrity.** ``dataset_hash`` recomputed from the files themselves. ``seal_dataset`` refuses a
  reconstructed tape, so the demo pack can never be sealed and therefore can never be claimed against;
  ``verify_dataset`` is what ``run_backtest`` calls before it reads a single market.

The demo pack is the one exemption, and it is narrow by construction: an **unsealed** dataset whose only
provider is ``demo`` skips the twelve-month window and the freeze checks of section 5.6, because its
markets resolved between 2016 and 2024. Every other check still applies to it, and no other dataset gets
the exemption (section 7.1).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pmx.data.schema import manifest_from_payload, market_from_payload, news_item_from_payload
from pmx.errors import (
    DatasetHashMismatchError,
    LeakError,
    NonCanonicalValueError,
    SchemaError,
    SealError,
)
from pmx.types import (
    JOURNAL_ENCODING,
    JOURNAL_NEWLINE,
    MS_PER_DAY,
    Dataset,
    DatasetFile,
    DatasetManifest,
    Market,
    NewsItem,
    bar_of,
    day_key,
    day_start_ms,
    interval_ms,
    meta_of,
    month_edges_for,
    ms_from_iso_date,
    sha256_hex,
    sort_market_metas,
)

MANIFEST_NAME = "manifest.json"
MARKETS_DIR = "markets"
NEWS_DIR = "news"
WIKI_ASOF_DIR = "wiki_asof"
#: The three directories the dataset hash covers, in the order the hash walks them. ``cache/`` and
#: ``contamination.json`` are deliberately outside it: one is disposable, the other is per-model and
#: changes without the data changing (sections 7.1 and 11.5).
HASHED_DIRS = (MARKETS_DIR, NEWS_DIR, WIKI_ASOF_DIR)


# --------------------------------------------------------------------------------------------------
# 4.2 Bytes on disk
# --------------------------------------------------------------------------------------------------
def read_canonical_text(path: Path) -> str:
    """Read a text artefact as UTF-8 with LF endings, refusing a carriage return.

    A ``\\r`` is rejected and never normalised: the development platform is Windows, where the default
    text mode rewrites ``\\n`` to ``\\r\\n`` and would leave the in-memory hash right and the bytes on
    disk wrong (section 4.2).
    """
    raw = path.read_bytes()
    if b"\r" in raw:
        raise NonCanonicalValueError("file carries a carriage return", path=str(path))
    try:
        return raw.decode(JOURNAL_ENCODING)
    except UnicodeDecodeError as exc:
        raise NonCanonicalValueError("file is not valid UTF-8", path=str(path)) from exc


def read_json_file(path: Path) -> object:
    """One canonical JSON file as a Python object."""
    text = read_canonical_text(path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError("file is not valid JSON", path=str(path), detail=exc.msg) from exc


def write_canonical_json(path: Path, payload: object) -> int:
    """Write ``canonical_json(payload) + "\\n"`` and return the byte count.

    ``canonical_json`` belongs to ``pmx.journal`` (section 4.1) and is the only encoder in pmx; it is
    imported inside the function so that the read path of this module does not depend on the journal.
    """
    from pmx.journal import canonical_json

    body = (canonical_json(payload) + JOURNAL_NEWLINE).encode(JOURNAL_ENCODING)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return len(body)


def write_canonical_jsonl(path: Path, payloads: Sequence[object]) -> int:
    """Write one canonical JSON object per line and return the byte count."""
    from pmx.journal import canonical_json

    body = "".join(canonical_json(payload) + JOURNAL_NEWLINE for payload in payloads).encode(JOURNAL_ENCODING)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return len(body)


# --------------------------------------------------------------------------------------------------
# 4.3 The dataset hash
# --------------------------------------------------------------------------------------------------
def dataset_files(path: Path) -> tuple[DatasetFile, ...]:
    """Every hashed file of the dataset, by relative POSIX path ascending by code point.

    ``manifest.json`` is excluded because it carries the hash; its own integrity is the ``sealed`` flag
    plus the recomputation ``verify_dataset`` performs (section 4.3).
    """
    entries: list[DatasetFile] = []
    for directory in HASHED_DIRS:
        root = path / directory
        if not root.is_dir():
            continue
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file():
                continue
            raw = candidate.read_bytes()
            entries.append(
                DatasetFile(
                    path=candidate.relative_to(path).as_posix(),
                    sha256=sha256_hex(raw),
                    bytes=len(raw),
                )
            )
    return tuple(sorted(entries, key=lambda entry: entry.path))


def dataset_hash_of(files: Iterable[DatasetFile]) -> str:
    """``sha256`` of ``"<relpath> <sha256>\\n"`` per file, sorted by relative path (section 4.3).

    The digest is over the *listing*, not over a concatenation of the files, so a reviewer can see which
    file moved by diffing two manifests instead of re-reading a year of tape.
    """
    listing = "\n".join(f"{entry.path} {entry.sha256}" for entry in sorted(files, key=lambda e: e.path))
    return sha256_hex((listing + "\n").encode(JOURNAL_ENCODING))


@dataclass(frozen=True, slots=True)
class DatasetVerification:
    """The report ``verify_dataset`` builds before it decides to raise.

    It exists because the HTTP surface answers ``{"ok", "dataset_hash", "expected", "mismatched_files"}``
    (section 12.12) and an exception cannot carry a list of files to a JSON response.
    """

    ok: bool
    dataset_hash: str
    expected: str
    mismatched_files: tuple[str, ...]
    missing_files: tuple[str, ...]
    extra_files: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "dataset_hash": self.dataset_hash,
            "expected": self.expected,
            "mismatched_files": list(self.mismatched_files),
            "missing_files": list(self.missing_files),
            "extra_files": list(self.extra_files),
        }


# --------------------------------------------------------------------------------------------------
# 7.2 One market file
# --------------------------------------------------------------------------------------------------
def check_market_structure(market: Market, *, manifest: DatasetManifest | None = None) -> None:
    """Everything about a market the JSON schema cannot say. Raises ``SchemaError`` or ``LeakError``."""
    if manifest is not None and market.interval_min != manifest.interval_min:
        raise SchemaError(
            "market grid differs from the dataset grid",
            market_id=market.id,
            market_interval_min=market.interval_min,
            dataset_interval_min=manifest.interval_min,
        )
    if not market.id.startswith(market.provider + "-"):
        raise SchemaError("market id does not start with its provider", market_id=market.id)
    if market.currency == "mana" and market.provider != "manifold":
        raise SchemaError("mana is Manifold's currency only", market_id=market.id, provider=market.provider)
    if market.provider == "manifold" and market.currency != "mana":
        raise SchemaError("a Manifold market is priced in mana", market_id=market.id)
    if not market.created_at_ms < market.close_at_ms:
        raise SchemaError(
            "created_at_ms must be before close_at_ms",
            market_id=market.id,
            created_at_ms=market.created_at_ms,
            close_at_ms=market.close_at_ms,
        )
    if not market.close_at_ms <= market.resolved_at_ms:
        raise SchemaError(
            "close_at_ms must be at or before resolved_at_ms",
            market_id=market.id,
            close_at_ms=market.close_at_ms,
            resolved_at_ms=market.resolved_at_ms,
        )
    _check_bars(market)
    _check_trades(market)
    if market.final_price_bp != market.bars[-1].close_bp:
        raise SchemaError(
            "final_price_bp is the close of the last bar",
            market_id=market.id,
            final_price_bp=market.final_price_bp,
            last_close_bp=market.bars[-1].close_bp,
        )
    if tuple(sorted(set(market.tags))) != market.tags:
        raise SchemaError("tags must be sorted and unique", market_id=market.id, tags=list(market.tags))
    if tuple(sorted(set(market.wiki_subjects))) != market.wiki_subjects:
        raise SchemaError("wiki_subjects must be sorted and unique", market_id=market.id)
    # The provenance flags are positional (section 7.2): flag k describes subject k, so a list of
    # another length describes nothing at all. Market.__post_init__ fills an empty list with
    # stated, so the only way to reach this is a file that carries a wrong-length list of its own.
    if len(market.wiki_subject_provenance) != len(market.wiki_subjects):
        raise SchemaError(
            "wiki_subject_provenance must carry one flag per wiki_subject",
            market_id=market.id,
            n_subjects=len(market.wiki_subjects),
            n_flags=len(market.wiki_subject_provenance),
        )
    if tuple(sorted(set(market.hardness_tags))) != market.hardness_tags:
        raise SchemaError("hardness_tags must be sorted and unique", market_id=market.id)
    if manifest is not None:
        _check_market_window(market, manifest=manifest)


def _check_bars(market: Market) -> None:
    step = interval_ms(market.interval_min)
    bars = market.bars
    expected_first = bar_of(market.created_at_ms, market.interval_min)
    expected_last = bar_of(market.resolved_at_ms, market.interval_min)
    if bars[0].t_ms != expected_first:
        raise SchemaError(
            "the first bar must open the bar containing created_at_ms",
            market_id=market.id,
            first_bar_ms=bars[0].t_ms,
            expected=expected_first,
        )
    if bars[-1].t_ms != expected_last:
        raise SchemaError(
            "the last bar must open the bar containing resolved_at_ms",
            market_id=market.id,
            last_bar_ms=bars[-1].t_ms,
            expected=expected_last,
        )
    for index, bar in enumerate(bars):
        if bar.t_ms % step != 0:
            raise SchemaError("bar is off the grid", market_id=market.id, t_ms=bar.t_ms, step=step)
        if index > 0 and bar.t_ms - bars[index - 1].t_ms != step:
            raise SchemaError(
                "bars must be dense on the grid, no gap and no duplicate",
                market_id=market.id,
                t_ms=bar.t_ms,
                previous_t_ms=bars[index - 1].t_ms,
                step=step,
            )
        if bar.low_bp > min(bar.open_bp, bar.close_bp, bar.vwap_bp) or bar.high_bp < max(
            bar.open_bp, bar.close_bp, bar.vwap_bp
        ):
            raise SchemaError("bar range does not contain its own prices", market_id=market.id, t_ms=bar.t_ms)
        if bar.yes_bid_bp is not None and bar.yes_ask_bp is not None and bar.yes_bid_bp > bar.yes_ask_bp:
            raise SchemaError("bid above ask", market_id=market.id, t_ms=bar.t_ms)
        if bar.volume_milli == 0 and bar.n_trades != 0:
            raise SchemaError("a zero-volume bar has no trades", market_id=market.id, t_ms=bar.t_ms)


def _check_trades(market: Market) -> None:
    keyed = [(trade.t_ms, trade.price_bp, trade.size_milli, trade.side) for trade in market.trades]
    if keyed != sorted(keyed):
        raise SchemaError("trades are out of canonical order", market_id=market.id, n_trades=len(keyed))


def _window_days(manifest: DatasetManifest) -> int:
    """``window_days`` as the build declared it, falling back to the span of the stated window.

    The value lives in ``filters.config``, which is ``BuildConfig.to_dict()`` verbatim and therefore
    untyped by the time it reaches here; the fallback keeps a hand-written manifest readable instead of
    unloadable.
    """
    declared = manifest.filters.config.get("window_days")
    if isinstance(declared, int) and not isinstance(declared, bool) and declared > 0:
        return declared
    return max(1, (manifest.window.end_ms - manifest.window.start_ms) // MS_PER_DAY)


def _check_market_window(market: Market, *, manifest: DatasetManifest) -> None:
    """The window and freeze rules of section 5.6, skipped for the demo pack and for nothing else.

    The rule is relative to the freeze, not to the stated window: a manifest whose window disagrees with
    its own freeze would otherwise smuggle a market of any age into a sealed dataset.
    """
    if manifest.is_demo_pack:
        return
    if market.resolved_at_ms >= manifest.freeze_ms:
        raise LeakError(
            "market resolves at or after the freeze",
            market_id=market.id,
            resolved_at_ms=market.resolved_at_ms,
            freeze_ms=manifest.freeze_ms,
        )
    if market.resolved_at_ms >= manifest.freeze_ms - MS_PER_DAY:
        raise SchemaError(
            "the freeze day and the day before it are outside the window",
            market_id=market.id,
            resolved_at_ms=market.resolved_at_ms,
            freeze_ms=manifest.freeze_ms,
        )
    window_start_ms = manifest.freeze_ms - _window_days(manifest) * MS_PER_DAY
    if market.resolved_at_ms < window_start_ms:
        raise SchemaError(
            "market resolves before the window opens",
            market_id=market.id,
            resolved_at_ms=market.resolved_at_ms,
            window_start_ms=window_start_ms,
        )
    if not manifest.window.start_ms <= market.resolved_at_ms < manifest.window.end_ms:
        raise SchemaError(
            "market resolves outside the dataset window",
            market_id=market.id,
            resolved_at_ms=market.resolved_at_ms,
            window_start_ms=manifest.window.start_ms,
            window_end_ms=manifest.window.end_ms,
        )


def load_market_file(path: Path, *, manifest: DatasetManifest | None = None) -> Market:
    """Load, validate and structurally check one ``markets/<id>.json``."""
    market = market_from_payload(read_json_file(path), where=path.name)
    if path.stem != market.id:
        raise SchemaError("market file name does not match its id", path=path.name, market_id=market.id)
    check_market_structure(market, manifest=manifest)
    return market


# --------------------------------------------------------------------------------------------------
# 7.3 One news file
# --------------------------------------------------------------------------------------------------
def check_news_item(item: NewsItem, *, manifest: DatasetManifest) -> None:
    """The as-of and leak rules of sections 5.5, 5.6, 7.1 and 7.3."""
    expected_visible = item.published_at_ms + manifest.safety_lag_ms
    if item.visible_from_ms != expected_visible:
        raise SchemaError(
            "visible_from_ms must be published_at_ms plus the dataset safety lag",
            news_id=item.news_id,
            visible_from_ms=item.visible_from_ms,
            expected=expected_visible,
            safety_lag_ms=manifest.safety_lag_ms,
        )
    if item.published_at_ms > manifest.freeze_ms and not manifest.is_demo_pack:
        raise LeakError(
            "news item published after the freeze",
            news_id=item.news_id,
            published_at_ms=item.published_at_ms,
            freeze_ms=manifest.freeze_ms,
        )
    if item.kind != _KIND_BY_SOURCE[item.source]:
        raise SchemaError(
            "kind contradicts source",
            news_id=item.news_id,
            source=item.source,
            kind=item.kind,
            expected=_KIND_BY_SOURCE[item.source],
        )
    if not item.news_id.startswith(_CODE_BY_SOURCE[item.source] + "-"):
        raise SchemaError("news id prefix contradicts source", news_id=item.news_id, source=item.source)
    if len(item.match_ids) != len(item.match_scores_permille):
        raise SchemaError(
            "match_scores_permille must be as long as match_ids",
            news_id=item.news_id,
            n_ids=len(item.match_ids),
            n_scores=len(item.match_scores_permille),
        )
    if tuple(sorted(set(item.match_ids))) != item.match_ids:
        raise SchemaError("match_ids must be sorted and unique", news_id=item.news_id)
    if tuple(sorted(set(item.wiki_links))) != item.wiki_links:
        raise SchemaError("wiki_links must be sorted and unique", news_id=item.news_id)
    if item.source == "wikipedia_asof":
        if item.revid is None or item.asof_day is None:
            raise SchemaError("a background snapshot names its revision and its day", news_id=item.news_id)
        limit = ms_from_iso_date(item.asof_day) + MS_PER_DAY
        if item.published_at_ms > limit:
            raise LeakError(
                "background snapshot is newer than the day it claims",
                news_id=item.news_id,
                published_at_ms=item.published_at_ms,
                asof_day=item.asof_day,
                limit=limit,
            )
    elif item.revid is not None or item.asof_day is not None:
        raise SchemaError("only a background snapshot carries revid and asof_day", news_id=item.news_id)


_KIND_BY_SOURCE = {
    "wikipedia_current_events": "headline",
    "wikipedia_asof": "background",
    "wayback": "frontpage",
    "gdelt": "article",
    "manifold_comment": "comment",
}
_CODE_BY_SOURCE = {
    "wikipedia_current_events": "wce",
    "wikipedia_asof": "wasof",
    "wayback": "wb",
    "gdelt": "gd",
    "manifold_comment": "mfc",
}


def load_news_file(path: Path, *, manifest: DatasetManifest) -> tuple[NewsItem, ...]:
    """Load one ``news/<yyyymmdd>.jsonl``: one item per line, ordered, all of the file's own day.

    The day key of the file is ``day_start_ms(published_at_ms)``, which for a Wikipedia Current events
    page of day ``D`` is ``D + 1`` while the item's id names ``D`` (sections 5.5 and 7.1). Checking the
    key here is what keeps the two spellings from ever drifting: ``wce-20160623-0007`` lives in
    ``news/20160624.jsonl``.
    """
    text = read_canonical_text(path)
    expected_day = path.stem
    items: list[NewsItem] = []
    for number, line in enumerate(text.split(JOURNAL_NEWLINE), start=1):
        if not line:
            continue
        try:
            payload: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SchemaError("news line is not valid JSON", path=path.name, line=number) from exc
        item = news_item_from_payload(payload, where=f"{path.name}:{number}")
        check_news_item(item, manifest=manifest)
        if day_key(day_start_ms(item.published_at_ms)) != expected_day:
            raise SchemaError(
                "news item is in the wrong day file",
                news_id=item.news_id,
                path=path.name,
                day_of_item=day_key(day_start_ms(item.published_at_ms)),
            )
        items.append(item)
    keyed = [(item.published_at_ms, item.news_id) for item in items]
    if keyed != sorted(keyed):
        raise SchemaError("news items are out of canonical order", path=path.name, n_items=len(items))
    return tuple(items)


def load_news(path: Path, *, manifest: DatasetManifest) -> tuple[NewsItem, ...]:
    """Every item of ``news/``, in file order then line order: the dataset order of section 3."""
    root = path / NEWS_DIR
    if not root.is_dir():
        return ()
    items: list[NewsItem] = []
    for candidate in sorted(root.glob("*.jsonl")):
        items.extend(load_news_file(candidate, manifest=manifest))
    return tuple(items)


def load_background_file(path: Path, *, manifest: DatasetManifest, market_id: str) -> NewsItem:
    """One ``wiki_asof/<market_id>/<yyyymmdd>.json`` snapshot."""
    item = news_item_from_payload(read_json_file(path), where=path.name)
    check_news_item(item, manifest=manifest)
    if item.source != "wikipedia_asof":
        raise SchemaError("wiki_asof holds background snapshots only", news_id=item.news_id, path=path.name)
    if market_id not in item.match_ids:
        raise SchemaError(
            "a background snapshot names the market it was fetched for",
            news_id=item.news_id,
            market_id=market_id,
            match_ids=list(item.match_ids),
        )
    return item


def load_background(path: Path, *, manifest: DatasetManifest, market_id: str) -> tuple[NewsItem, ...]:
    """Every background snapshot of one market, oldest first."""
    root = path / WIKI_ASOF_DIR / market_id
    if not root.is_dir():
        return ()
    items = [
        load_background_file(candidate, manifest=manifest, market_id=market_id)
        for candidate in sorted(root.glob("*.json"))
    ]
    return tuple(sorted(items, key=lambda item: (item.published_at_ms, item.news_id)))


# --------------------------------------------------------------------------------------------------
# 7.8 The dataset
# --------------------------------------------------------------------------------------------------
def load_manifest(path: Path) -> DatasetManifest:
    """The manifest of the dataset directory ``path``, validated and cross-checked.

    ``freeze_ms`` is recomputed from ``freeze_date`` rather than trusted: the pair is the one place in
    the design where a human-readable convenience sits next to the integer the engine reads, and a
    mismatch there would move every window silently.
    """
    manifest_path = path / MANIFEST_NAME
    if not manifest_path.is_file():
        raise SchemaError("dataset has no manifest", path=str(path))
    manifest = manifest_from_payload(read_json_file(manifest_path), where=MANIFEST_NAME)
    expected_freeze = ms_from_iso_date(manifest.freeze_date)
    if manifest.freeze_ms != expected_freeze:
        raise SchemaError(
            "freeze_ms does not match freeze_date",
            freeze_date=manifest.freeze_date,
            freeze_ms=manifest.freeze_ms,
            expected=expected_freeze,
        )
    if manifest.window.start_ms >= manifest.window.end_ms:
        raise SchemaError(
            "the dataset window is empty",
            start_ms=manifest.window.start_ms,
            end_ms=manifest.window.end_ms,
        )
    missing = [key for key in _REMOVED_KEYS if key not in manifest.filters.removed]
    if missing:
        raise SchemaError("filters.removed is missing keys", missing=missing)
    unknown = [key for key in manifest.filters.removed if key not in _REMOVED_KEYS]
    if unknown:
        raise SchemaError("filters.removed carries unknown keys", unknown=unknown)
    if manifest.split.month_edges_ms != _expected_edges(manifest):
        raise SchemaError(
            "the month edges are not section 7.7's formula over the window",
            window_start_ms=manifest.window.start_ms,
        )
    return manifest


_REMOVED_KEYS = (
    "window",
    "opened_early",
    "binary",
    "min_trades",
    "min_life",
    "density",
    "self_resolved",
    "kalshi_shards",
    "resolution",
    "no_leak",
)


def _expected_edges(manifest: DatasetManifest) -> tuple[int, ...]:
    return month_edges_for(manifest.window.start_ms)


def load_dataset(path: Path, *, verify: bool = False) -> Dataset:
    """Load a dataset directory: the manifest, every market's metadata, and lazy access to the tapes.

    Every market file is opened and fully validated here, because the leak-free ``MarketMeta`` the
    metrics and the optimizer read carries the fold, the resolution and the bar count, and a dataset that
    is half readable is not a dataset. The **tape** of a market is loaded on first use through
    ``Dataset.market``, which is why a year of hourly bars over three hundred markets does not have to
    fit in memory at once.

    ``verify`` is keyword-only and defaults to false, because ``run_backtest`` calls ``verify_dataset``
    itself before it reads a market (section 7.8) and the builder loads a dataset whose manifest hash is
    still being computed.
    """
    manifest = load_manifest(path)
    if verify:
        verify_dataset(path, manifest=manifest)
    markets_dir = path / MARKETS_DIR
    if not markets_dir.is_dir():
        raise SchemaError("dataset has no markets directory", path=str(path))
    metas = []
    for candidate in sorted(markets_dir.glob("*.json")):
        market = load_market_file(candidate, manifest=manifest)
        if market.provider not in manifest.providers:
            raise SchemaError(
                "market provider is not one of the dataset's",
                market_id=market.id,
                provider=market.provider,
                providers=list(manifest.providers),
            )
        metas.append(meta_of(market, fold=manifest.split.fold_of(market.resolved_at_ms)))
    if not metas:
        raise SchemaError("dataset holds no market", path=str(path))
    if len(metas) != manifest.counts.markets:
        raise SchemaError(
            "the manifest's market count is not the number of market files",
            counted=len(metas),
            manifest_count=manifest.counts.markets,
        )
    return Dataset(
        manifest=manifest,
        metas=sort_market_metas(metas),
        path=path,
        market_loader=lambda market_id: load_market_file(
            path / MARKETS_DIR / f"{market_id}.json", manifest=manifest
        ),
        news_loader=lambda: load_news(path, manifest=manifest),
        background_loader=lambda market_id: load_background(path, manifest=manifest, market_id=market_id),
    )


def verify_dataset(path: Path, *, manifest: DatasetManifest | None = None) -> DatasetVerification:
    """Recompute the file digests and the dataset hash; raise ``DatasetHashMismatchError`` on any
    difference.

    This is the check that makes a claim mean something: a score is a statement about these bytes, so a
    one-byte edit to a market file has to be fatal rather than interesting. ``run_backtest`` calls it
    before reading a single market.
    """
    report = verify_dataset_report(path, manifest=manifest)
    if not report.ok:
        raise DatasetHashMismatchError(
            "dataset hash does not match its manifest",
            path=str(path),
            dataset_hash=report.dataset_hash,
            expected=report.expected,
            mismatched_files=list(report.mismatched_files),
            missing_files=list(report.missing_files),
            extra_files=list(report.extra_files),
        )
    return report


def verify_dataset_report(path: Path, *, manifest: DatasetManifest | None = None) -> DatasetVerification:
    """The non-raising half of ``verify_dataset``: what ``GET /datasets/{name}/verify`` answers."""
    resolved = manifest if manifest is not None else load_manifest(path)
    found = dataset_files(path)
    recomputed = dataset_hash_of(found)
    declared = {entry.path: entry for entry in resolved.files}
    present = {entry.path: entry for entry in found}
    mismatched = tuple(
        sorted(
            name
            for name, entry in present.items()
            if name in declared and (declared[name].sha256 != entry.sha256 or declared[name].bytes != entry.bytes)
        )
    )
    missing = tuple(sorted(name for name in declared if name not in present))
    extra = tuple(sorted(name for name in present if name not in declared))
    ok = recomputed == resolved.dataset_hash and not mismatched and not missing and not extra
    return DatasetVerification(
        ok=ok,
        dataset_hash=recomputed,
        expected=resolved.dataset_hash,
        mismatched_files=mismatched,
        missing_files=missing,
        extra_files=extra,
    )


def seal_dataset(path: Path) -> DatasetManifest:
    """Refuse a reconstructed market, recompute ``files`` and ``dataset_hash``, write ``sealed: true``.

    A sealed dataset is one that can carry a claim, so a reconstructed tape is refused here rather than
    flagged: the demo pack is a test vehicle, and a plausible price path is not evidence about a market
    (section 7.8). The write is the last step, so a refusal leaves the manifest as it was.
    """
    dataset = load_dataset(path)
    reconstructed = sorted(
        meta.id for meta in dataset.metas if dataset.market(meta.id).source == "reconstructed"
    )
    if reconstructed:
        raise SealError(
            "a reconstructed market cannot be sealed",
            path=str(path),
            market_ids=reconstructed,
            n=len(reconstructed),
        )
    files = dataset_files(path)
    manifest = dataset.manifest
    sealed = DatasetManifest(
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
        sealed=True,
        notes=manifest.notes,
    )
    write_manifest(path, sealed)
    return sealed


def write_manifest(path: Path, manifest: DatasetManifest) -> int:
    """Write ``manifest.json`` canonically and return the byte count."""
    return write_canonical_json(path / MANIFEST_NAME, manifest.to_dict())


def reseal_hash(path: Path, manifest: DatasetManifest) -> DatasetManifest:
    """The same recomputation as ``seal_dataset`` without setting ``sealed``.

    The builder and the migration need a manifest whose ``files`` and ``dataset_hash`` describe what was
    just written, and the demo pack needs exactly that while staying unsealed and unclaimable
    (section 7.8: "The demo pack carries ``sealed: false`` and a valid hash so it is reproducible without
    being claimable").
    """
    files = dataset_files(path)
    return DatasetManifest(
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
        sealed=manifest.sealed,
        notes=manifest.notes,
    )
