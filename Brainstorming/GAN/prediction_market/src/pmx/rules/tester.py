"""Pre-registered families, the fit screen, the FDR step, out-of-time replication and the live record.

CONTRACTS_V2 18.2 steps 1 to 8, package S2, as amended by the arbitration of rulings R276 to R302. The
tester is a projection of the dataset and of the journals that proposed the rules: it writes no
**backtest** journal, it never reads the sealed fold (architecture rule 3), and it refuses a
``purpose: "showcase"`` dataset. Architecture rule 8 does **not** extend to it (ruling R294): it is the
one emitter of ``family_registered``, ``rule_tested``, ``rule_promoted`` and ``rule_demoted``, into the
evolution journal it is handed and into its own ledger, and it never writes a ``rule_proposed`` line,
which has one emitter in ``engine/runner.py``.

Four decisions of the arbitration are the reason this file looks the way it does, and each of them is the
opposite of a reading a first pass would have taken:

* **The live record is as-of** (ruling R276). At a bar ``b`` it covers the matched rows with
  ``fit_t1_ms + interval_ms <= t < b`` and nothing else. Not unbounded, or an agent trading month
  ``k + 2`` would see an insight demoted by what the validation months did, which 7.9 forbids by name;
  and **not** frozen at the replicate fold's edge either, which was the fix proposed and refused, because
  a record that never grows can never demote a rule that decays, which is the record's one job.
* **The rolling pair is clipped to the training fold** (ruling R277). ``k`` is an explicit argument drawn
  from the pairs whose month ``k + 1`` ends at or before ``train_end_ms``, never an inference, because
  under the count quantiles of R247 the calendar position of ``train_end_ms`` is data-dependent and an
  unclipped ``for k in 4..9`` replicates on validation or sealed months on any front-loaded distribution.
* **The rule path has its own null** (ruling R282). ``permutation_null`` is the claim path's and is not
  called here: its arguments have no meaning for a rule's matched ``(market, bar)`` rows and it scores a
  Brier skill against the market, which fails exactly the rule 18.2 calls useful. The rule's p-value is
  the ``(b + 1) / (B + 1)`` estimator over shuffles of the firing labels **within each block**, on the
  same statistic promotion tests, and it can never be zero, which is what makes it comparable against a
  Benjamini-Hochberg threshold of ``k * q / m``.
* **The family id names the data** (ruling R284), not only the generation and the template, so
  ``--rolling 4``, ``--rolling 5`` and ``--headline`` on one dataset are three families and not one id
  with three payloads.

``benjamini_hochberg`` and ``rule_permutation_p_ppm`` are **E4's** names in ``pmx.metrics.stats`` by the
agreement recorded in section 13 (rulings R238 and R282). That file belongs to another package and is not
written here; the two private functions below are the same statistics, spelled once, and the module-level
comment on each says what replaces it. They are integer-only and draw through ``pmx.rng``'s registered
``stats.permutation`` substream, so nothing new is registered and no numpy crosses architecture rule 4.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pmx import journal as journal_module
from pmx.errors import InvalidConfigError, NotConfiguredError, PmxError, SchemaError
from pmx.journal import Journal, JournalEvent, canonical_json, canonical_sha256
from pmx.metrics.stats import (
    Interval,
    _benjamini_hochberg_k,
    benjamini_hochberg,
    bootstrap_lower_bound,
    iso_week_key,
    rule_permutation_p_ppm,
)
from pmx.rng import RngTree
from pmx.rules.rule import (
    RE_FAMILY_ID,
    RULE_MIN_MARKETS,
    Rule,
    RuleClaim,
    RuleRefusedError,
    RuleScope,
    outcome_bp,
)
from pmx.rules.vocabulary import FeatureBlock, SensorBlockLike
from pmx.types import (
    FDR_Q_PPM,
    PPM_ONE,
    DatasetSplit,
    MarketMeta,
    bar_of,
    bp_ratio,
    default_horizons_bars,
    interval_ms,
    round_half_up,
    sha256_hex,
)

__all__ = (
    "FDR_Q_PPM",
    "LEDGER_DIR_NAME",
    "RE_FAMILY_ID",
    "RULE_FAMILY_SCREENED_MAX",
    "RULE_LIVE_MIN_SUPPORT",
    "RULE_PERMUTATIONS_MAX",
    "RULE_PERMUTATIONS_MIN",
    "RULE_ROLLING_K_RANGE",
    "RULE_VOLATILITY_USUAL_MIN_ROWS",
    "TEST_STAGES",
    "BarRow",
    "FamilyResult",
    "FamilyTemplate",
    "FoldPair",
    "HypothesisFamily",
    "LiveRecord",
    "MarketRows",
    "Promotion",
    "RowTable",
    "RuleLedger",
    "RuleTester",
    "ScopeRow",
    "TestRecord",
    "mean_half_away",
    "family_id_of",
    "headline_pair",
    "permutations_for",
    "rolling_ks",
    "rolling_pair",
    "row_table_from_dict",
    "scope_rows",
    "usual_bp_for",
)

#: The permutation count follows the family (ruling R282).
RULE_PERMUTATIONS_MIN = 200
RULE_PERMUTATIONS_MAX = 20_000

#: ``RULE_PERMUTATIONS_MAX * FDR_Q_PPM // PPM_ONE``: a family nobody can resolve is refused, not tested.
RULE_FAMILY_SCREENED_MAX = RULE_PERMUTATIONS_MAX * FDR_Q_PPM // PPM_ONE

#: Matched rows a live record needs before it may demote a rule (18.2 step 7, a default).
RULE_LIVE_MIN_SUPPORT = 30

#: The ``k`` of a rolling pair, before the clip to ``train_end_ms`` (12.7, ruling R277).
RULE_ROLLING_K_RANGE: tuple[int, ...] = (4, 5, 6, 7, 8, 9)

#: Rows a ``(scope, horizon)`` needs on the fit fold before its ``usual_bp`` median is trusted.
#: 18.2 leaves this floor to S2 (BUILD_STATE 9.6b): a median over five rows is not a "usual" move, and a
#: volatility claim measured against one is noise with a unit. A default the first build reports against.
RULE_VOLATILITY_USUAL_MIN_ROWS = 30

#: The four stages a ``rule_tested`` row can carry (9.4).
TEST_STAGES: tuple[str, ...] = ("fit", "replicate", "live", "transfer")

#: Where the ledger lives, under the repository root (9.5): ``rules/<dataset_hash[:8]>/``.
LEDGER_DIR_NAME = "rules"

_FAMILIES_FILE = "families.jsonl"
_RULES_FILE = "rules.jsonl"

#: The four events 9.3 gives this module, and the ``pmx.journal`` dataclass each will be emitted through
#: once gate G4 lands them with O2's evolution journal (9.4: they are declared, not yet in the catalogue).
_EVENT_CLASSES: Mapping[str, str] = {
    "family_registered": "FamilyRegistered",
    "rule_tested": "RuleTested",
    "rule_promoted": "RulePromoted",
    "rule_demoted": "RuleDemoted",
}


# --------------------------------------------------------------------------------------------------
# The rows a rule is tested on
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BarRow:
    """One completed bar of one market: its open, its close and the sensor blocks of that bar.

    The tester has no agent, so the blocks are the **whole catalogue's** (ruling R279) and a ledger
    interval is a full-diet statement that means one thing for everybody. ``close_bp`` is the price in bp
    on a binary and the instrument's price in its own scale on a continuous kind, where every measurement
    goes through ``bp_ratio`` and the scale cancels.
    """

    t_ms: int
    close_bp: int
    blocks: Mapping[str, SensorBlockLike]


@dataclass(frozen=True, slots=True)
class MarketRows:
    """Every bar of one market, ascending, with the leak-free meta and the resample block of 12.4.

    ``fold_key_ms`` is the resolution bar of the latest member of the market's cluster or ``event_key``
    group (7.7, ruling R290), which is what the fold cut is taken on so that no group spans two folds. It
    defaults to the market's own ``resolved_at_ms``, which is the same number on an ungrouped market and
    is what a dataset built before the fold fix can offer.
    """

    meta: MarketMeta
    bars: tuple[BarRow, ...]
    block: str
    fold_key_ms: int

    def __post_init__(self) -> None:
        times = [bar.t_ms for bar in self.bars]
        if times != sorted(times):
            raise SchemaError("a market's bars are not ascending", market_id=self.meta.id)

    @property
    def last_bar_ms(self) -> int:
        """The open of the last completed bar, or ``0`` for a market with no bar."""
        return self.bars[-1].t_ms if self.bars else 0


@dataclass(frozen=True, slots=True)
class RowTable:
    """The dataset as the hypothesis layer reads it: metas, bars, blocks, block keys and the fold cuts.

    This is the tester's and the miner's whole world. It is deliberately not a ``Dataset``: a rule is
    evaluated on sensor blocks, which are a projection of an observation (18.1) and are computed by S1
    from the same as-of views an agent receives, and the same table is what FM1's proxy matrix fills per
    ``(market, bar)`` with no observation in sight. Building one from a sealed dataset plus S1's catalogue
    is the ``pmx rules`` command's job once S1 ships; until then a table is loaded from disk, which is
    also how the planted-effect fixture of AC-27 travels.
    """

    dataset_hash: str
    interval_min: int
    split: DatasetSplit
    markets: tuple[MarketRows, ...]
    purpose: str = "research"

    def __post_init__(self) -> None:
        if self.purpose == "showcase":
            raise ShowcaseRowsError(
                "a showcase dataset has no folds and no claims, so it has no rules either",
                dataset_hash=self.dataset_hash,
            )
        ids = [rows.meta.id for rows in self.markets]
        if ids != sorted(ids):
            raise SchemaError("a row table is ordered by market id", dataset_hash=self.dataset_hash)

    @property
    def interval(self) -> int:
        """The grid step in milliseconds."""
        return interval_ms(self.interval_min)

    def in_scope(self, scope: RuleScope) -> tuple[MarketRows, ...]:
        """The markets of the table inside ``scope``, in canonical order, sealed months excluded.

        The exclusion is architecture rule 3 applied at the only place the tester chooses rows: a market
        of the sealed fold is never a row of any stage, promotion, live record or transfer test.
        """
        return tuple(
            rows for rows in self.markets if rows.meta.fold != "sealed" and scope.matches(rows.meta)
        )

    def facets(self) -> Mapping[str, tuple[str, ...]]:
        """The providers, categories and kinds the table carries, sorted: the transfer test's targets."""
        return {
            "providers": tuple(sorted({rows.meta.provider for rows in self.markets})),
            "categories": tuple(sorted({rows.meta.category for rows in self.markets})),
            "kinds": tuple(sorted({rows.meta.kind for rows in self.markets})),
        }


class ShowcaseRowsError(PmxError):
    """A showcase dataset reached the hypothesis layer (12.7).

    13.1 gives this refusal to ``pmx.errors`` as ``ShowcaseDatasetError``, added there by DS1 in the same
    lot (18.8's deferral table). It is spelled here, in this package's own file, while that file is held
    by another package in the same tree; the move is a one-line import and no caller outside S2 raises it.
    """


def _meta_from_dict(payload: Mapping[str, object]) -> MarketMeta:
    """A ``MarketMeta`` from its ``to_dict()`` (7.2), which is how a row table travels on disk.

    The five taxonomy fields of amendment C1c are read with their defaults, so a row table written before
    the taxonomy comes back exactly as it did. Reading them is not optional decoration: ``cohort_id`` is
    derived from the four facets (18.5), so a reader that dropped them would answer ``None`` on every row
    of a tagged dataset and ``RuleScope.cohorts`` (18.2) would match nothing at all on a row table, which
    is a rule silently claiming to hold nowhere rather than a rule refused.
    """
    return MarketMeta(
        id=str(payload["id"]),
        provider=str(payload["provider"]),
        category=str(payload["category"]),
        tags=tuple(str(tag) for tag in _as_list(payload.get("tags", ()))),
        event_key=None if payload.get("event_key") is None else str(payload["event_key"]),
        created_at_ms=int(str(payload["created_at_ms"])),
        close_at_ms=int(str(payload["close_at_ms"])),
        resolved_at_ms=int(str(payload["resolved_at_ms"])),
        resolution=int(str(payload["resolution"])),
        interval_min=int(str(payload["interval_min"])),
        n_bars=int(str(payload["n_bars"])),
        hardness_tags=tuple(str(tag) for tag in _as_list(payload.get("hardness_tags", ()))),
        fee_schedule_id=str(payload["fee_schedule_id"]),
        fold=str(payload["fold"]),
        kind=str(payload.get("kind", "binary")),
        subject=tuple(str(value) for value in _as_list(payload.get("subject", ()))),
        structure=str(payload.get("structure") or ""),
        horizon=str(payload.get("horizon") or ""),
        provider_labels=tuple(str(value) for value in _as_list(payload.get("provider_labels", ()))),
    )


def _as_list(value: object) -> Sequence[object]:
    if isinstance(value, list | tuple):
        return value
    raise SchemaError("expected a list in a row table", value=repr(value))


def _as_mapping(value: object, *, what: str) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    raise SchemaError(f"expected an object for {what}", value=repr(value))


def row_table_from_dict(payload: Mapping[str, object]) -> RowTable:
    """Read a row table from its on-disk form (the shape ``tests/fixtures/s2/`` ships).

    ``{dataset_hash, interval_min, purpose, split: {...}, markets: [{meta, block, fold_key_ms, bars:
    [{t_ms, close_bp, blocks: {sensor: [values]}}]}]}``. The blocks are plain integer lists in the
    catalogue's own feature order, which is the only order 18.1 defines, so a fixture cannot disagree with
    a sensor about which position a feature sits at.
    """
    split_payload = _as_mapping(payload["split"], what="split")
    edges = tuple(int(str(edge)) for edge in _as_list(split_payload["month_edges_ms"]))
    markets: list[MarketRows] = []
    for entry in _as_list(payload["markets"]):
        record = _as_mapping(entry, what="a market")
        meta = _meta_from_dict(_as_mapping(record["meta"], what="a meta"))
        bars: list[BarRow] = []
        for bar_entry in _as_list(record["bars"]):
            bar = _as_mapping(bar_entry, what="a bar")
            blocks: dict[str, SensorBlockLike] = {}
            for sensor, values in _as_mapping(bar["blocks"], what="the blocks of a bar").items():
                blocks[sensor] = FeatureBlock(
                    sensor=sensor, values=tuple(int(str(value)) for value in _as_list(values))
                )
            bars.append(
                BarRow(t_ms=int(str(bar["t_ms"])), close_bp=int(str(bar["close_bp"])), blocks=blocks)
            )
        markets.append(
            MarketRows(
                meta=meta,
                bars=tuple(bars),
                block=str(record.get("block") or _default_block(meta)),
                fold_key_ms=int(str(record.get("fold_key_ms", meta.resolved_at_ms))),
            )
        )
    counts = {"train": 0, "validation": 0, "sealed": 0}
    for rows in markets:
        counts[rows.meta.fold] = counts.get(rows.meta.fold, 0) + 1
    split = DatasetSplit(
        month_edges_ms=edges,
        train_end_ms=int(str(split_payload["train_end_ms"])),
        validation_end_ms=int(str(split_payload["validation_end_ms"])),
        n_train=counts["train"],
        n_validation=counts["validation"],
        n_sealed=counts["sealed"],
    )
    return RowTable(
        dataset_hash=str(payload["dataset_hash"]),
        interval_min=int(str(payload["interval_min"])),
        split=split,
        markets=tuple(sorted(markets, key=lambda rows: rows.meta.id)),
        purpose=str(payload.get("purpose", "research")),
    )


def _default_block(meta: MarketMeta) -> str:
    """12.4's block key without a cluster: the event key, else the ISO week of the resolution."""
    return meta.event_key if meta.event_key is not None else iso_week_key(meta.resolved_at_ms)


# --------------------------------------------------------------------------------------------------
# The fold pairs a promotion may read (18.2 step 5, ruling R277)
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FoldPair:
    """Two disjoint chronological folds and the two instants a family is anchored on.

    ``registered_at_ms`` is the fit fold's last bar (the data the template was drawn on) and
    ``fit_t1_ms`` the replicate fold's last bar, which is the visibility anchor of every promotion of the
    family and the bar the promotion never reads past. Both are properties of the **fold**, computed
    before any rule is read, because they enter ``family_id`` and the family is registered before a single
    replicate row is touched. The last bar of a fold is the latest of its markets' last completed bar and
    of the bar their resolution falls in, so a bias claim, which reads an outcome rather than a price,
    cannot reach past it either.
    """

    fit_fold: str
    replicate_fold: str
    fit_ids: tuple[str, ...]
    replicate_ids: tuple[str, ...]
    registered_at_ms: int
    fit_t1_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "fit_fold": self.fit_fold,
            "replicate_fold": self.replicate_fold,
            "n_fit_markets": len(self.fit_ids),
            "n_replicate_markets": len(self.replicate_ids),
            "registered_at_ms": self.registered_at_ms,
            "fit_t1_ms": self.fit_t1_ms,
        }


def _last_bar_of(table: RowTable, ids: Sequence[str]) -> int:
    """The last bar a fold can offer: the latest bar open and the latest resolution bar of its markets."""
    wanted = set(ids)
    last = 0
    for rows in table.markets:
        if rows.meta.id not in wanted:
            continue
        last = max(last, rows.last_bar_ms, bar_of(rows.meta.resolved_at_ms, table.interval_min))
    return last


def _pair(
    table: RowTable,
    *,
    fit_fold: str,
    replicate_fold: str,
    fit: Sequence[str],
    replicate: Sequence[str],
) -> FoldPair:
    if not fit or not replicate:
        raise InvalidConfigError(
            "a fold pair needs markets on both sides; O1's make_folds raises FoldIntegrityError on the "
            "same condition and its remedy is 7.4's fallback order, never a silently narrower test",
            fit_fold=fit_fold,
            replicate_fold=replicate_fold,
            n_fit=len(fit),
            n_replicate=len(replicate),
        )
    return FoldPair(
        fit_fold=fit_fold,
        replicate_fold=replicate_fold,
        fit_ids=tuple(sorted(fit)),
        replicate_ids=tuple(sorted(replicate)),
        registered_at_ms=_last_bar_of(table, fit),
        fit_t1_ms=_last_bar_of(table, replicate),
    )


def headline_pair(table: RowTable) -> FoldPair:
    """``(train, validation)``: the pair L1 and the claim path read (``pmx rules test --headline``)."""
    fit = [rows.meta.id for rows in table.markets if rows.meta.fold == "train"]
    replicate = [rows.meta.id for rows in table.markets if rows.meta.fold == "validation"]
    return _pair(table, fit_fold="train", replicate_fold="validation", fit=fit, replicate=replicate)


def rolling_ks(split: DatasetSplit) -> tuple[int, ...]:
    """The ``k`` of 12.7's rolling pairs, **clipped to the training fold** (ruling R277).

    ``k`` in ``4..9`` whose month ``k + 1`` ends at or before ``train_end_ms``, ascending, possibly fewer
    than six and possibly none. The clip is the whole ruling: under R247's count quantiles the calendar
    position of ``train_end_ms`` is data-dependent, so an unclipped range replicates a rule on a
    validation or a sealed month on any distribution whose resolutions bunch early.
    """
    edges = split.month_edges_ms
    return tuple(k for k in RULE_ROLLING_K_RANGE if k + 1 < len(edges) and edges[k + 1] <= split.train_end_ms)


def rolling_pair(table: RowTable, k: int) -> FoldPair:
    """``(months 1..k, month k + 1)``: the pair every evolution generation uses.

    ``k`` is an explicit argument drawn from :func:`rolling_ks` and never inferred; the evolution uses the
    largest of them. Membership is by ``fold_key_ms``, the group's resolution bar, so no cluster is split
    between the fit months and the replicate month.
    """
    available = rolling_ks(table.split)
    if k not in available:
        raise InvalidConfigError(
            "a rolling k must be one of the pairs whose replicate month ends at or before train_end_ms",
            k=k,
            available=list(available),
        )
    edges = table.split.month_edges_ms
    fit = [rows.meta.id for rows in table.markets if edges[0] <= rows.fold_key_ms < edges[k]]
    replicate = [rows.meta.id for rows in table.markets if edges[k] <= rows.fold_key_ms < edges[k + 1]]
    return _pair(
        table, fit_fold=f"m1..m{k}", replicate_fold=f"m{k + 1}", fit=fit, replicate=replicate
    )


# --------------------------------------------------------------------------------------------------
# The family (18.2 step 1, ruling R284)
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FamilyTemplate:
    """The grammar of a family: what may vary and what is fixed (18.2)."""

    scope_keys: tuple[str, ...]
    features: tuple[str, ...]
    claim_kind: str
    horizon_bars: int
    author_kind: str

    def to_dict(self) -> dict[str, object]:
        return {
            "scope_keys": list(self.scope_keys),
            "features": list(self.features),
            "claim_kind": self.claim_kind,
            "horizon_bars": self.horizon_bars,
            "author_kind": self.author_kind,
        }


def family_id_of(
    *,
    dataset_hash: str,
    generation: int,
    fit_fold: str,
    replicate_fold: str,
    registered_at_ms: int,
    fit_t1_ms: int,
    template: FamilyTemplate,
) -> str:
    """Ruling R284's content address: the id names the **data** the family was drawn on, not only its
    grammar, so three runs over one dataset are three families and the pre-registration guard cannot be
    satisfied by the wrong registration."""
    payload = [
        dataset_hash,
        generation,
        fit_fold,
        replicate_fold,
        registered_at_ms,
        fit_t1_ms,
        template.to_dict(),
    ]
    return "hf-" + canonical_sha256(payload)[:16]


@dataclass(frozen=True, slots=True)
class HypothesisFamily:
    """A pre-registered family (18.2 step 1, ruling R284)."""

    family_id: str
    dataset_hash: str
    generation: int
    fit_fold: str
    replicate_fold: str
    template: FamilyTemplate
    n_candidates: int
    n_screened: int
    fit_t1_ms: int
    registered_at_ms: int

    def __post_init__(self) -> None:
        if not RE_FAMILY_ID.match(self.family_id):
            raise RuleRefusedError("a malformed family id", reason="bad_rule", family_id=self.family_id)
        expected = family_id_of(
            dataset_hash=self.dataset_hash,
            generation=self.generation,
            fit_fold=self.fit_fold,
            replicate_fold=self.replicate_fold,
            registered_at_ms=self.registered_at_ms,
            fit_t1_ms=self.fit_t1_ms,
            template=self.template,
        )
        if self.family_id != expected:
            raise RuleRefusedError(
                "a family id is the hash of its data and its grammar",
                reason="bad_rule",
                family_id=self.family_id,
                expected=expected,
            )
        if self.n_screened > self.n_candidates:
            raise RuleRefusedError(
                "a family screened more rules than it enumerated",
                reason="bad_rule",
                n_candidates=self.n_candidates,
                n_screened=self.n_screened,
            )

    def to_dict(self) -> dict[str, object]:
        """The ``family_registered`` payload of 9.4, plus the three fields every ledger line carries."""
        return {
            "family_id": self.family_id,
            "dataset_hash": self.dataset_hash,
            "generation": self.generation,
            "fit_fold": self.fit_fold,
            "replicate_fold": self.replicate_fold,
            "template": self.template.to_dict(),
            "n_candidates": self.n_candidates,
            "n_screened": self.n_screened,
            "fit_t1_ms": self.fit_t1_ms,
            "registered_at_ms": self.registered_at_ms,
        }


# --------------------------------------------------------------------------------------------------
# What one test answers
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TestRecord:
    """One ``rule_tested`` row (9.4): one rule, one stage, every number that decided it."""

    rule_id: str
    family_id: str
    stage: str
    fold: str
    target: str | None
    support: int
    n_markets: int
    effect: Interval
    usual_bp: int | None
    p_value_ppm: int | None
    fdr_m: int | None
    fdr_k: int | None
    fdr_passed: bool | None
    passed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "family_id": self.family_id,
            "stage": self.stage,
            "fold": self.fold,
            "target": self.target,
            "support": self.support,
            "n_markets": self.n_markets,
            "effect": self.effect.to_dict(),
            "usual_bp": self.usual_bp,
            "p_value_ppm": self.p_value_ppm,
            "fdr_m": self.fdr_m,
            "fdr_k": self.fdr_k,
            "fdr_passed": self.fdr_passed,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class Promotion:
    """A promoted rule and the two instants that decide when anybody may see it (18.2 step 6)."""

    rule: Rule
    family_id: str
    fit: TestRecord
    replicate: TestRecord
    fit_t1_ms: int
    visible_from_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule.rule_id,
            "family_id": self.family_id,
            "author_kind": self.rule.author_kind,
            "author_id": self.rule.author_id,
            "fit_t1_ms": self.fit_t1_ms,
            "visible_from_ms": self.visible_from_ms,
        }


@dataclass(frozen=True, slots=True)
class LiveRecord:
    """The as-of live record of a promoted rule at a bar ``b`` (ruling R276)."""

    rule_id: str
    from_ms: int
    to_ms: int
    live_support: int
    live_n_markets: int
    live_interval: Interval
    demote: bool
    reason: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "from_ms": self.from_ms,
            "to_ms": self.to_ms,
            "live_support": self.live_support,
            "live_n_markets": self.live_n_markets,
            "live_interval": self.live_interval.to_dict(),
            "demote": self.demote,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class FamilyResult:
    """Everything one family produced: its registration, its rows and its promotions."""

    family: HypothesisFamily
    fit: tuple[TestRecord, ...]
    replicate: tuple[TestRecord, ...]
    promotions: tuple[Promotion, ...]
    permutations: int


# --------------------------------------------------------------------------------------------------
# The measurement of 18.2's table
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ScopeRow:
    """One ``(market, bar)`` row in a rule's scope: its measurement, whether the rule fired, its block."""

    market_id: str
    t_ms: int
    y_bp: int
    fired: bool
    block: str


def _target_index(rows: MarketRows, index: int, horizon: int) -> int | None:
    if rows.meta.kind == "binary":
        # Binary horizons use the fixed UTC grid, even when proposal rows have been sampled.
        # Continuous instruments retain their trading-bar horizons across session gaps.
        expected = rows.bars[index].t_ms + horizon * interval_ms(rows.meta.interval_min)
        target = bisect_left(rows.bars, expected, key=lambda bar: bar.t_ms)
        if target >= len(rows.bars) or rows.bars[target].t_ms != expected:
            return None
        return target
    target = index + horizon
    return target if target < len(rows.bars) else None


def _delta_bp(rows: MarketRows, index: int, horizon: int) -> int | None:
    """``price_{t+h} - price_t`` in bp on a binary, ``bp_ratio`` of it on a continuous kind.

    ``None`` when the ``h``-th completed bar after ``t`` does not exist before the bar the market resolved
    in, which is 18.2's skip rule and not a zero.
    """
    target = _target_index(rows, index, horizon)
    if target is None:
        return None
    resolution_bar = bar_of(rows.meta.resolved_at_ms, rows.meta.interval_min)
    if rows.bars[target].t_ms >= resolution_bar:
        return None
    start = rows.bars[index].close_bp
    end = rows.bars[target].close_bp
    if rows.meta.kind == "binary":
        return end - start
    if start == 0:
        return None
    return bp_ratio(end - start, start)


def target_available_at_ms(rows: MarketRows, index: int, claim: RuleClaim, horizon: int) -> int | None:
    """When a row's realised target can first be read by a later observation (MVP-6).

    Trigger time alone cannot bound a live score: a past trigger can still depend on an unresolved
    outcome or an unfinished horizon bar. Resolutions become visible after their settle bar.
    """
    span = interval_ms(rows.meta.interval_min)
    if claim.kind == "bias" and rows.meta.kind == "binary":
        return bar_of(rows.meta.resolved_at_ms, rows.meta.interval_min) + span
    target = _target_index(rows, index, horizon)
    if target is None:
        return None
    return rows.bars[target].t_ms + span


def _median(values: Sequence[int]) -> int:
    """The integer median, halves rounded up on an even count: ``usual_bp`` is a non-negative move."""
    if not values:
        return 0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return round_half_up(ordered[middle - 1] + ordered[middle], 2)


def _usual_moves(table: RowTable, scope: RuleScope, *, horizon_bars: int, ids: Sequence[str]) -> list[int]:
    """The absolute moves behind ``usual_bp``: every row of ``ids`` in ``scope``, matched or not."""
    wanted = set(ids)
    moves: list[int] = []
    for rows in table.in_scope(scope):
        if rows.meta.id not in wanted:
            continue
        for index in range(len(rows.bars)):
            delta = _delta_bp(rows, index, horizon_bars)
            if delta is not None:
                moves.append(abs(delta))
    return moves


def usual_bp_for(table: RowTable, scope: RuleScope, *, horizon_bars: int, ids: Sequence[str]) -> int:
    """The median absolute move of **every** row of the fit fold in ``scope``, matched or not (18.2).

    Computed once per ``(scope, horizon)`` from the **fit** fold and recorded in the test record, on every
    stage: a volatility claim is an excess over the usual, and re-estimating the baseline on each fold
    would silently re-centre the claim, so a rule that held once would hold again by construction.
    """
    return _median(_usual_moves(table, scope, horizon_bars=horizon_bars, ids=ids))


def scope_rows(
    table: RowTable,
    rule: Rule,
    *,
    ids: Sequence[str],
    usual_bp: int,
    from_ms: int | None = None,
    to_ms: int | None = None,
    scope: RuleScope | None = None,
    available_at_ms: int | None = None,
) -> tuple[ScopeRow, ...]:
    """Every measurable row of ``ids`` in scope, with its ``y_row`` and whether the rule fired.

    Public because the miner ranks the same rows this builds and must not build them a second way: one
    row builder means the mean the search sorts by and the ``point`` the interval reports are the same
    integer over the same rows.

    ``from_ms`` and ``to_ms`` are the half-open bar window ``[from, to)`` the caller may read: the live
    record and the transfer test are both windows over the same rows, which is why there is one row
    builder and not three. ``scope`` overrides the rule's own, which is what a transfer target is: the
    target's values are the ones the rule's scope does **not** name (see ``RuleTester._targets``), so
    selecting on the target already selects outside the rule.

    The scope is applied once, per market, by ``effective``; what marks a row is then the **condition**
    alone (``Rule.condition_holds``), which is ``Rule.fires`` minus the market test already made. That is
    what lets a transfer test ask what the condition does on a provider the rule's scope excludes, which
    is the one question ``fires`` could not answer there.
    """
    wanted = set(ids)
    effective = scope if scope is not None else rule.scope
    claim = rule.claim
    horizon = rule.horizon_bars if claim.kind != "bias" else default_horizons_bars(table.interval_min)[0]
    out: list[ScopeRow] = []
    for rows in table.markets:
        if rows.meta.fold == "sealed" or rows.meta.id not in wanted:
            continue
        if not effective.matches(rows.meta):
            continue
        for index, bar in enumerate(rows.bars):
            if from_ms is not None and bar.t_ms < from_ms:
                continue
            if to_ms is not None and bar.t_ms >= to_ms:
                continue
            if available_at_ms is not None:
                ready = target_available_at_ms(rows, index, claim, horizon)
                if ready is None or ready > available_at_ms:
                    continue
            value = _measure(rows, index, claim, horizon)
            if value is None:
                continue
            if claim.kind == "volatility":
                value -= usual_bp
            out.append(
                ScopeRow(
                    market_id=rows.meta.id,
                    t_ms=bar.t_ms,
                    y_bp=value,
                    fired=rule.condition_holds(bar.blocks),
                    block=rows.block,
                )
            )
    return tuple(out)


def _measure(rows: MarketRows, index: int, claim: RuleClaim, horizon: int) -> int | None:
    """18.2's table for one row, before the volatility subtraction of ``usual_bp``."""
    if claim.kind == "bias":
        if rows.meta.kind == "binary":
            if rows.meta.resolution not in (0, 1):
                return None
            return claim.direction * (outcome_bp(rows.meta.resolution) - rows.bars[index].close_bp)
        delta = _delta_bp(rows, index, horizon)
        return None if delta is None else claim.direction * delta
    delta = _delta_bp(rows, index, horizon)
    if delta is None:
        return None
    if claim.kind == "drift":
        return claim.direction * delta
    return abs(delta)


# --------------------------------------------------------------------------------------------------
# The two statistics E4 owns by the agreement of section 13 (rulings R238 and R282)
# --------------------------------------------------------------------------------------------------
# ``benjamini_hochberg`` and ``rule_permutation_p_ppm`` now live where 12.4 declares them, in E4's
# ``pmx.metrics.stats``, added there by the agreement recorded in section 13; the two stand-ins this
# module carried while that file belonged to another package in flight are gone, and the tester calls
# the contracted names. ``_benjamini_hochberg_k`` comes from the same module for the reason its own
# docstring gives: the threshold ``p_(k) * m <= k * q_ppm`` is spelled once, and a second spelling of
# it here is exactly the drift that made the flag loop and the ledger's ``fdr_k`` disagree.


def mean_half_away(total: int, count: int) -> int:
    """``round(total / count)`` half away from zero, in integers, so a loss and its mirror agree."""
    if count == 0:
        return 0
    negative = total < 0
    quotient = round_half_up(abs(total), count)
    return -quotient if negative else quotient


def permutations_for(n_screened: int) -> int:
    """``min(RULE_PERMUTATIONS_MAX, max(RULE_PERMUTATIONS_MIN, 20 * n_screened))`` (ruling R282)."""
    return min(RULE_PERMUTATIONS_MAX, max(RULE_PERMUTATIONS_MIN, 20 * n_screened))


# --------------------------------------------------------------------------------------------------
# The ledger on disk (9.5, 18.2)
# --------------------------------------------------------------------------------------------------
@dataclass
class RuleLedger:
    """``rules/<dataset_hash[:8]>/families.jsonl`` and ``rules.jsonl``, chained as ``claims/`` is chained.

    Tracked, not generated scratch: the ledger is the evidence a hypothesis was written down before it was
    tested, and a negative result is a first-class row of it. Each line carries ``dataset_hash``,
    ``fit_fold`` and ``replicate_fold`` (ruling R284), which is exactly the key the duplicate rule of step
    4 is defined on, and ``prev_sha256``, the sha256 of the previous line's bytes in the same file
    (``null`` for the first), so a deleted line breaks the chain and is detectable.
    """

    root: Path
    dataset_hash: str
    _families_prev: str | None = field(default=None, init=False, repr=False)
    _rules_prev: str | None = field(default=None, init=False, repr=False)

    @property
    def directory(self) -> Path:
        return self.root / LEDGER_DIR_NAME / self.dataset_hash[:8]

    @property
    def families_path(self) -> Path:
        return self.directory / _FAMILIES_FILE

    @property
    def rules_path(self) -> Path:
        return self.directory / _RULES_FILE

    def _tail(self, path: Path) -> str | None:
        if not path.is_file():
            return None
        last: str | None = None
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.rstrip("\n")
                if stripped:
                    last = stripped
        return None if last is None else sha256_hex(last.encode("utf-8"))

    def append(self, path: Path, payload: Mapping[str, object]) -> str:
        """Append one canonical line, chained to the previous one, and return the line."""
        previous = self._families_prev if path == self.families_path else self._rules_prev
        if previous is None:
            previous = self._tail(path)
        line = canonical_json({**payload, "prev_sha256": previous})
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
        digest = sha256_hex(line.encode("utf-8"))
        if path == self.families_path:
            self._families_prev = digest
        else:
            self._rules_prev = digest
        return line

    def read(self, path: Path) -> tuple[Mapping[str, object], ...]:
        """Every line of one ledger file, in order, as mappings."""
        if not path.is_file():
            return ()
        out: list[Mapping[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(_as_mapping(json.loads(line), what="a ledger line"))
        return tuple(out)

    def verify(self, path: Path) -> None:
        """Walk the chain and raise ``SchemaError`` on the first break."""
        previous: str | None = None
        if not path.is_file():
            return
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            payload = _as_mapping(json.loads(line), what="a ledger line")
            stated = payload.get("prev_sha256")
            if stated != previous:
                raise SchemaError(
                    "the rule ledger's chain is broken", path=str(path), line=number, expected=previous
                )
            previous = sha256_hex(line.encode("utf-8"))

    def families(self) -> tuple[Mapping[str, object], ...]:
        return self.read(self.families_path)

    def rules(self) -> tuple[Mapping[str, object], ...]:
        return self.read(self.rules_path)


# --------------------------------------------------------------------------------------------------
# The tester
# --------------------------------------------------------------------------------------------------
class RuleTester:
    """18.2's procedure: screen on the fit fold, register, control the family's FDR, replicate, promote.

    One instance per ``(row table, ledger)``. It is the one emitter of the four rule events (ruling R294)
    and writes them into its ledger always and into the evolution journal it was handed when it has one.
    """

    __slots__ = ("_generation", "_journal", "_ledger", "_rng", "_table", "_tested")

    def __init__(
        self,
        table: RowTable,
        *,
        rng: RngTree,
        ledger: RuleLedger,
        generation: int = 0,
        journal: Journal | None = None,
    ) -> None:
        self._table = table
        self._rng = rng
        self._ledger = ledger
        self._generation = generation
        self._journal = journal
        self._tested: set[tuple[str, str, str]] = set()
        for row in ledger.rules():
            if row.get("type") == "rule_tested" and row.get("stage") == "replicate":
                self._tested.add(
                    (str(row.get("rule_id")), str(row.get("fit_fold")), str(row.get("replicate_fold")))
                )

    @property
    def table(self) -> RowTable:
        return self._table

    @property
    def ledger(self) -> RuleLedger:
        return self._ledger

    # -- journal and ledger --------------------------------------------------------------------
    def _emit(self, event: str, payload: Mapping[str, object]) -> None:
        """Emit one of the four events into the evolution journal, when there is one (ruling R294).

        The four ``pmx.journal`` dataclasses are declared in ``journal.v2.json`` and land with O2's
        evolution journal at gate G4 (9.4). Until then a tester handed a journal says so rather than
        dropping an event on the floor: an event this module owns has exactly one writer, and a silent
        skip would make the ledger and the journal disagree about what happened.
        """
        if self._journal is None:
            return
        candidate = getattr(journal_module, _EVENT_CLASSES[event], None)
        if not (isinstance(candidate, type) and issubclass(candidate, JournalEvent)):
            raise NotConfiguredError(
                "this journal cannot carry a rule event yet: pmx.journal gains the four dataclasses with "
                "O2's evolution journal at gate G4 (9.4). Run the tester without a journal until then; "
                "the ledger carries every row either way",
                event=event,
                dataclass=_EVENT_CLASSES[event],
            )
        self._journal.emit(candidate, bar_ms=0, phase="generation", **dict(payload))

    def _ledger_line(self, path: Path, event: str, pair: FoldPair, payload: Mapping[str, object]) -> None:
        self._ledger.append(
            path,
            {
                "type": event,
                "dataset_hash": self._table.dataset_hash,
                "fit_fold": pair.fit_fold,
                "replicate_fold": pair.replicate_fold,
                "generation": self._generation,
                **payload,
            },
        )

    # -- step 1: pre-registration -------------------------------------------------------------
    def register_family(
        self, template: FamilyTemplate, pair: FoldPair, *, n_candidates: int, n_screened: int
    ) -> HypothesisFamily:
        """Write the family down (18.2 step 1). Nothing may read a replicate row before this returns."""
        if n_screened > RULE_FAMILY_SCREENED_MAX:
            raise RuleRefusedError(
                "a family nobody can resolve is a family the miner must split by template",
                reason="family_too_large",
                n_screened=n_screened,
                maximum=RULE_FAMILY_SCREENED_MAX,
            )
        family = HypothesisFamily(
            family_id=family_id_of(
                dataset_hash=self._table.dataset_hash,
                generation=self._generation,
                fit_fold=pair.fit_fold,
                replicate_fold=pair.replicate_fold,
                registered_at_ms=pair.registered_at_ms,
                fit_t1_ms=pair.fit_t1_ms,
                template=template,
            ),
            dataset_hash=self._table.dataset_hash,
            generation=self._generation,
            fit_fold=pair.fit_fold,
            replicate_fold=pair.replicate_fold,
            template=template,
            n_candidates=n_candidates,
            n_screened=n_screened,
            fit_t1_ms=pair.fit_t1_ms,
            registered_at_ms=pair.registered_at_ms,
        )
        self._ledger_line(self._ledger.families_path, "family_registered", pair, family.to_dict())
        self._emit(
            "family_registered",
            {
                "generation": self._generation,
                "family_id": family.family_id,
                "template": template.to_dict(),
                "n_candidates": n_candidates,
                "n_screened": n_screened,
                "fit_t1_ms": family.fit_t1_ms,
                "registered_at_ms": family.registered_at_ms,
            },
        )
        return family

    def is_registered(self, family_id: str) -> bool:
        """Has this family a ``family_registered`` line in the ledger already? (18.2 step 1's guard.)"""
        return any(str(row.get("family_id")) == family_id for row in self._ledger.families())

    def is_duplicate(self, rule: Rule, pair: FoldPair) -> bool:
        """Was this content already replicated on this ``(dataset_hash, fit, replicate)``? (step 4.)"""
        return (rule.rule_id, pair.fit_fold, pair.replicate_fold) in self._tested

    # -- the measurement -----------------------------------------------------------------------
    def _interval(self, rows: Sequence[ScopeRow]) -> tuple[Interval, int, int]:
        matched = [row for row in rows if row.fired]
        values = [row.y_bp for row in matched]
        blocks = [row.block for row in matched]
        interval = bootstrap_lower_bound(values, blocks, rng=self._rng)
        return interval, len(matched), len({row.market_id for row in matched})

    def _usual(self, rule: Rule, pair: FoldPair) -> tuple[int | None, int]:
        """``(usual_bp, the rows behind it)``, always over the **fit** fold (18.2's table).

        ``None`` on a bias or a drift claim, which measure no excess. The row count is what the floor of
        :data:`RULE_VOLATILITY_USUAL_MIN_ROWS` is checked against, so a claim is refused for the median it
        was measured against and never for the size of the fold it is being tested on.
        """
        if rule.claim.kind != "volatility":
            return None, 0
        moves = _usual_moves(self._table, rule.scope, horizon_bars=rule.horizon_bars, ids=pair.fit_ids)
        return _median(moves), len(moves)

    def _holds(self, rule: Rule, interval: Interval, support: int, n_markets: int, usual_rows: int) -> bool:
        """18.2's "a claim holds": support, distinct markets and a positive lower bound.

        A volatility claim also needs enough rows behind its ``usual_bp`` median (this module's own floor,
        BUILD_STATE 9.6b): an excess over an unstable baseline is not a measurement.
        """
        if rule.claim.kind == "volatility" and usual_rows < RULE_VOLATILITY_USUAL_MIN_ROWS:
            return False
        return (
            support >= rule.min_support
            and n_markets >= RULE_MIN_MARKETS
            and interval.n_blocks >= 2
            and interval.lower > 0
        )

    def test_on_fold(
        self,
        rule: Rule,
        pair: FoldPair,
        *,
        stage: str,
        family_id: str,
        ids: Sequence[str],
        target: str | None = None,
        from_ms: int | None = None,
        to_ms: int | None = None,
        scope: RuleScope | None = None,
        p_value_ppm: int | None = None,
        fdr_m: int | None = None,
        fdr_k: int | None = None,
        fdr_passed: bool | None = None,
        permutations: int | None = None,
    ) -> tuple[TestRecord, tuple[ScopeRow, ...]]:
        """Measure one rule on one set of markets and write the ``rule_tested`` row.

        ``permutations`` reaches the **ledger** line and never the journal event, which is the one place
        18.2 and 9.4 disagree. 18.2 step 3 says the replicate row carries ``p_value_ppm``,
        ``permutations``, ``m``, ``k`` and ``fdr_passed``; 9.4's catalogue row lists fourteen fields
        without ``permutations``, and ``journal.v2.json``'s ``rule_tested`` closes its object with
        ``unevaluatedProperties: false``, so a fifteenth field would fail the contract's own validator at
        gate G4. The ledger file is this package's and already carries what the event cannot (the rule
        itself, the dataset hash and the fold pair), so the count is recorded there and the journal keeps
        the shape 9.4 states. Widening a schema C1c owns is not S2's to do, so the disagreement is
        reported rather than resolved here.
        """
        if stage not in TEST_STAGES:
            raise RuleRefusedError("an unknown test stage", reason="bad_rule", stage=stage)
        if stage == "replicate" and not self.is_registered(family_id):
            raise RuleRefusedError(
                "the family has no earlier family_registered line, so no replicate row may be read",
                reason="unregistered_family",
                family_id=family_id,
                rule_id=rule.rule_id,
            )
        usual, usual_rows = self._usual(rule, pair)
        rows = scope_rows(
            self._table,
            rule,
            ids=ids,
            usual_bp=usual or 0,
            from_ms=from_ms,
            to_ms=to_ms,
            scope=scope,
        )
        interval, support, n_markets = self._interval(rows)
        passed = self._holds(rule, interval, support, n_markets, usual_rows)
        if fdr_passed is not None:
            passed = passed and fdr_passed
        fold = pair.fit_fold if stage == "fit" else pair.replicate_fold
        record = TestRecord(
            rule_id=rule.rule_id,
            family_id=family_id,
            stage=stage,
            fold=fold,
            target=target,
            support=support,
            n_markets=n_markets,
            effect=interval,
            usual_bp=usual,
            p_value_ppm=p_value_ppm,
            fdr_m=fdr_m,
            fdr_k=fdr_k,
            fdr_passed=fdr_passed,
            passed=passed,
        )
        self._ledger_line(
            self._ledger.rules_path,
            "rule_tested",
            pair,
            {**record.to_dict(), "permutations": permutations, "rule": rule.to_dict()},
        )
        self._emit("rule_tested", {"generation": self._generation, **record.to_dict()})
        if stage == "replicate":
            self._tested.add((rule.rule_id, pair.fit_fold, pair.replicate_fold))
        return record, rows

    # -- steps 2 to 6: the whole procedure for one family --------------------------------------
    def run_family(
        self, candidates: Sequence[Rule], *, template: FamilyTemplate, pair: FoldPair, n_candidates: int
    ) -> FamilyResult:
        """Screen, register, control, replicate and promote (18.2 steps 2 to 6), in that order.

        The order is the contract's and is not an implementation detail: the fit screen reads the fit fold
        only, the family is written down with its two counts **before** a single replicate row is read,
        and the FDR step and the replication then read the replicate fold together.
        """
        for rule in candidates:
            if self.is_duplicate(rule, pair):
                raise RuleRefusedError(
                    "this content was already tested on this fold pair, so nobody re-rolls it",
                    reason="duplicate",
                    rule_id=rule.rule_id,
                    fit_fold=pair.fit_fold,
                    replicate_fold=pair.replicate_fold,
                )
        placeholder = family_id_of(
            dataset_hash=self._table.dataset_hash,
            generation=self._generation,
            fit_fold=pair.fit_fold,
            replicate_fold=pair.replicate_fold,
            registered_at_ms=pair.registered_at_ms,
            fit_t1_ms=pair.fit_t1_ms,
            template=template,
        )
        fit_records: list[TestRecord] = []
        fit_by_rule: dict[str, TestRecord] = {}
        screened: list[Rule] = []
        for rule in candidates:
            record, _rows = self.test_on_fold(
                rule, pair, stage="fit", family_id=placeholder, ids=pair.fit_ids
            )
            fit_records.append(record)
            fit_by_rule[rule.rule_id] = record
            if record.passed:
                screened.append(rule)
        family = self.register_family(
            template, pair, n_candidates=n_candidates, n_screened=len(screened)
        )
        permutations = permutations_for(len(screened))
        p_values: list[int] = []
        row_sets: list[tuple[ScopeRow, ...]] = []
        for rule in screened:
            usual, _rows_behind = self._usual(rule, pair)
            rows = scope_rows(self._table, rule, ids=pair.replicate_ids, usual_bp=usual or 0)
            row_sets.append(rows)
            p_values.append(
                rule_permutation_p_ppm(
                    [row.y_bp for row in rows],
                    [row.fired for row in rows],
                    [row.block for row in rows],
                    rng=self._rng,
                    permutations=permutations,
                )
            )
        flags = benjamini_hochberg(p_values)
        fdr_k = _benjamini_hochberg_k(p_values)
        replicate_records: list[TestRecord] = []
        promotions: list[Promotion] = []
        for position, rule in enumerate(screened):
            record, _rows = self.test_on_fold(
                rule,
                pair,
                stage="replicate",
                family_id=family.family_id,
                ids=pair.replicate_ids,
                p_value_ppm=p_values[position],
                fdr_m=len(screened),
                fdr_k=fdr_k,
                fdr_passed=flags[position],
                permutations=permutations,
            )
            replicate_records.append(record)
            if record.passed:
                promotions.append(self._promote(rule, family, pair, fit_by_rule[rule.rule_id], record))
        return FamilyResult(
            family=family,
            fit=tuple(fit_records),
            replicate=tuple(replicate_records),
            promotions=tuple(promotions),
            permutations=permutations,
        )

    def _promote(
        self, rule: Rule, family: HypothesisFamily, pair: FoldPair, fit: TestRecord, replicate: TestRecord
    ) -> Promotion:
        """Step 6: visibility follows the data, so an insight is visible one bar after what promoted it."""
        if not self.is_registered(family.family_id):
            raise RuleRefusedError(
                "no family_registered line precedes this promotion",
                reason="unregistered_family",
                family_id=family.family_id,
            )
        promotion = Promotion(
            rule=rule,
            family_id=family.family_id,
            fit=fit,
            replicate=replicate,
            fit_t1_ms=pair.fit_t1_ms,
            visible_from_ms=pair.fit_t1_ms + self._table.interval,
        )
        self._ledger_line(self._ledger.rules_path, "rule_promoted", pair, promotion.to_dict())
        self._emit(
            "rule_promoted",
            {
                "generation": self._generation,
                "rule_id": rule.rule_id,
                "family_id": family.family_id,
                "author_kind": rule.author_kind,
                "author_id": rule.author_id,
                "fit_t1_ms": promotion.fit_t1_ms,
                "visible_from_ms": promotion.visible_from_ms,
                "entry_id": "",
            },
        )
        return promotion

    # -- step 7: the live record, as-of ---------------------------------------------------------
    def live_record(
        self, promotion: Promotion, pair: FoldPair, *, at_ms: int, author_reputation: int | None = None
    ) -> LiveRecord:
        """The as-of live record at bar ``at_ms`` (ruling R276).

        The window is exactly ``[visible_from_ms, at_ms)``: the rows the rule fired on after its promotion
        was visible and strictly before the recomputing bar. Not unbounded, which would let month 11 demote
        an insight an agent is trading in month ``k + 2``, the field 7.9 forbids by name; and not frozen at
        the replicate fold's edge either, because a record that never grows can never demote a rule that
        decays. A trigger contributes only after its target bar has completed, or its binary settlement
        has become visible at the next observation (MVP-6). Sealed markets are excluded here.
        """
        rule = promotion.rule
        window_from = promotion.visible_from_ms
        ids = [rows.meta.id for rows in self._table.markets if rows.meta.fold != "sealed"]
        usual, _rows_behind = self._usual(rule, pair)
        rows = scope_rows(
            self._table, rule, ids=ids, usual_bp=usual or 0, from_ms=window_from, to_ms=at_ms,
            available_at_ms=at_ms,
        )
        interval, support, n_markets = self._interval(rows)
        reason: str | None = None
        if support >= RULE_LIVE_MIN_SUPPORT and interval.upper < 0:
            reason = "live_negative"
        elif author_reputation is not None and author_reputation < 0 and interval.lower <= 0:
            reason = "author_reputation"
        return LiveRecord(
            rule_id=rule.rule_id,
            from_ms=window_from,
            to_ms=at_ms,
            live_support=support,
            live_n_markets=n_markets,
            live_interval=interval,
            demote=reason is not None,
            reason=reason,
        )

    def demote(self, record: LiveRecord, pair: FoldPair) -> None:
        """Write the ``rule_demoted`` row. A demoted rule is never re-promoted by re-testing (18.2)."""
        if record.reason is None:
            raise RuleRefusedError(
                "a demotion needs a reason", reason="bad_rule", rule_id=record.rule_id
            )
        payload = {
            "rule_id": record.rule_id,
            "reason": record.reason,
            "live_support": record.live_support,
            "live_effect": record.live_interval.to_dict(),
            "demoted_at_ms": record.to_ms,
        }
        self._ledger_line(self._ledger.rules_path, "rule_demoted", pair, payload)
        self._emit("rule_demoted", {"generation": self._generation, **payload})

    # -- step 8: knowledge transfer -------------------------------------------------------------
    def transfer_tests(self, promotion: Promotion, pair: FoldPair) -> tuple[TestRecord, ...]:
        """Re-test a promoted rule on every provider, category and kind outside its scope (18.2 step 8).

        It reads the promotion's **own** replicate fold, restricted to the targets outside the scope, and
        no bar at or after ``visible_from_ms`` (ruling R276): a transfer test is a re-test of a promoted
        rule, not a licence to walk forward into the months its promotion never read. It never promotes
        anything and never widens a scope.
        """
        rule = promotion.rule
        out: list[TestRecord] = []
        for key, values in self._targets(rule.scope).items():
            for value in values:
                scope = RuleScope(**{key: (value,)})
                record, _rows = self.test_on_fold(
                    rule,
                    pair,
                    stage="transfer",
                    family_id=promotion.family_id,
                    ids=pair.replicate_ids,
                    target=f"{key}:{value}",
                    to_ms=promotion.visible_from_ms,
                    scope=scope,
                )
                out.append(record)
        return tuple(out)

    def _targets(self, scope: RuleScope) -> Mapping[str, tuple[str, ...]]:
        """The facet values of the dataset that lie **outside** the rule's scope.

        A facet the scope leaves empty is "any" (18.2), so it has no outside and contributes no target: a
        rule that already claims to hold on every category cannot be transferred to one. Only a facet the
        scope narrows produces targets, and only the values it did not name, which is what makes "outside
        the scope" a property of this mapping rather than a second filter over the rows: a market matching
        ``providers:manifold`` cannot match a scope whose providers are ``("kalshi",)``.
        """
        facets = self._table.facets()
        named = {"providers": scope.providers, "categories": scope.categories, "kinds": scope.kinds}
        return {
            key: () if not named[key] else tuple(value for value in facets[key] if value not in named[key])
            for key in ("categories", "kinds", "providers")
        }


def load_row_table(path: Path) -> RowTable:
    """Read a row table from a JSON document on disk."""
    return row_table_from_dict(_as_mapping(json.loads(path.read_text(encoding="utf-8")), what="a row table"))


def canonical_lines(rows: Iterable[Mapping[str, object]]) -> tuple[str, ...]:
    """Render ledger rows the way the files store them: one canonical JSON object per line (4.2)."""
    return tuple(canonical_json(row) for row in rows)
