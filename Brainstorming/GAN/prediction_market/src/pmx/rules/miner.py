"""The symbolic miner: a deterministic beam search for candidate rules on the fit fold.

CONTRACTS_V2 18.2, "Who proposes", package S2. The miner is one of three authors and the only one that
enumerates: an agent proposes at most one rule per bar and a detector states a finding it already had, but
the miner walks the vocabulary. That is why it is the one with a candidate budget, and why every candidate
it enumerates counts toward its family's ``n_candidates`` whether or not it reaches the bootstrap: a
family's Benjamini-Hochberg bar is only honest if the count of what was looked at is honest.

**No randomness at all.** The miner draws from no substream, and two runs on one dataset produce one
candidate list, byte for byte. Thresholds come from the feature's own quantiles over the fit fold's rows
in scope, the beam keeps the best ``RULE_MINER_BEAM`` by ``lift_bp`` with the support floor, and ties are
broken by the canonical order of the predicate tuple, which is a total order, so nothing is decided by a
dictionary's iteration order or by which of two equal candidates was seen first.

**What it scores with.** ``lift_bp`` is the interval's ``point``, and ``Interval.point`` is the observed
mean and never a resample statistic (12.4), so the search scores the plain integer mean of ``y_row`` over
the matched rows and never runs a bootstrap. The bootstrap belongs to the tester's fit screen, which the
survivors go through next: ten thousand block bootstraps of ten thousand resamples each would cost minutes
per family to rank candidates a mean already ranks identically.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pmx.rules.rule import (
    RULE_MIN_MARKETS,
    RULE_MIN_SUPPORT_DEFAULT,
    RULE_PREDICATES_MAX,
    Predicate,
    Rule,
    RuleClaim,
    RuleScope,
    make_rule,
)
from pmx.rules.tester import (
    FamilyTemplate,
    FoldPair,
    RowTable,
    ScopeRow,
    mean_half_away,
    scope_rows,
    usual_bp_for,
)
from pmx.rules.vocabulary import feature_ref, read_feature
from pmx.types import PPM_ONE, round_half_up

__all__ = (
    "MINER_AUTHOR_ID",
    "MINER_OPS",
    "RULE_MINER_BEAM",
    "RULE_MINER_CANDIDATES_MAX",
    "RULE_THRESHOLD_QUANTILES_PPM",
    "MinedCandidate",
    "MinerResult",
    "mine",
    "quantiles_ppm",
    "template_of",
)

#: Beam width of the search (18.2).
RULE_MINER_BEAM = 32

#: Candidates enumerated per family, at most (18.2). Every one of them counts in ``n_candidates``.
RULE_MINER_CANDIDATES_MAX = 10_000

#: The quantiles a threshold is drawn from, in ppm of the fit fold's rows in scope (18.2).
RULE_THRESHOLD_QUANTILES_PPM: tuple[int, ...] = (100_000, 250_000, 500_000, 750_000, 900_000)

#: The author id of every mined rule (18.7's author regex admits it by name).
MINER_AUTHOR_ID = "miner"

#: The operators the search enumerates on a quantile threshold. 18.2 fixes the thresholds and the beam
#: and leaves the operator set open; ``le`` and ``gt`` are the two that partition the rows at a
#: threshold, so the pair spans every split the quantiles can express and adds no redundant twin
#: (``lt``/``ge`` cut the same rows one unit over, ``eq``/``ne`` on a quantile of a wide integer range
#: match almost nothing). A default the first build reports against; widening it widens ``n_candidates``
#: and therefore the family's FDR bar, which is the honest cost of looking at more.
MINER_OPS: tuple[str, ...] = ("le", "gt")


@dataclass(frozen=True, slots=True)
class MinedCandidate:
    """One enumerated conjunction and what it measured on the fit fold."""

    rule: Rule
    lift_bp: int
    support: int
    n_markets: int

    @property
    def order_key(self) -> tuple[int, tuple[tuple[str, str, int], ...]]:
        """Best first: the highest lift, ties broken by the canonical order of the predicate tuple."""
        return (-self.lift_bp, tuple(predicate.sort_key for predicate in self.rule.condition))


@dataclass(frozen=True, slots=True)
class MinerResult:
    """What one mining pass produced: its candidates, its template and the count the family reports."""

    template: FamilyTemplate
    candidates: tuple[MinedCandidate, ...]
    n_candidates: int
    truncated: bool

    def rules(self) -> tuple[Rule, ...]:
        return tuple(candidate.rule for candidate in self.candidates)


def template_of(
    scope: RuleScope, features: Sequence[str], claim: RuleClaim, horizon_bars: int
) -> FamilyTemplate:
    """The family template a mining pass registers under: the grammar, never the thresholds.

    ``scope_keys`` names the scope keys the pass **fixed**, because those are the values that vary between
    one family and the next; the features are sorted and the claim kind and horizon are fixed, which is
    exactly what 18.2 says a template is.
    """
    keys = tuple(
        key
        for key in ("kinds", "providers", "categories", "tags", "cohorts")
        if getattr(scope, key)
    )
    return FamilyTemplate(
        scope_keys=keys,
        features=tuple(sorted(set(features))),
        claim_kind=claim.kind,
        horizon_bars=horizon_bars,
        author_kind="miner",
    )


def quantiles_ppm(values: Sequence[int], quantiles: Sequence[int] = RULE_THRESHOLD_QUANTILES_PPM) -> tuple[int, ...]:
    """The values at ``quantiles`` (in ppm) of ``values``, sorted, unique, by nearest rank.

    Nearest rank rather than an interpolation, because an interpolated quantile of integers is a float and
    a threshold has to be an integer in the feature's own unit. Duplicates are dropped: on a feature whose
    distribution is concentrated, three quantiles landing on one integer are one candidate and not three,
    which keeps ``n_candidates`` a count of distinct hypotheses.
    """
    if not values:
        return ()
    ordered = sorted(values)
    out: list[int] = []
    for quantile in quantiles:
        rank = round_half_up(quantile * (len(ordered) - 1), PPM_ONE)
        out.append(ordered[min(max(rank, 0), len(ordered) - 1)])
    return tuple(sorted(set(out)))


def _feature_values(table: RowTable, feature: str, *, scope: RuleScope, ids: Sequence[str]) -> tuple[int, ...]:
    """Every integer read of ``feature`` over the fit fold's rows in scope, in row order."""
    wanted = set(ids)
    out: list[int] = []
    for market in table.in_scope(scope):
        if market.meta.id not in wanted:
            continue
        for bar in market.bars:
            observed = read_feature(feature, bar.blocks)
            if observed is not None:
                out.append(observed)
    return tuple(out)


def _score(rows: Sequence[ScopeRow]) -> tuple[int, int, int]:
    """The mean of ``y_row``, the support and the distinct markets of one conjunction over ``rows``.

    The mean is the tester's own ``mean_half_away``, which is what ``Interval.point`` reports, so the
    order the beam keeps is the order the fit screen would have measured.
    """
    total = 0
    support = 0
    markets: set[str] = set()
    for row in rows:
        if not row.fired:
            continue
        total += row.y_bp
        support += 1
        markets.add(row.market_id)
    if support == 0:
        return 0, 0, 0
    return mean_half_away(total, support), support, len(markets)


def mine(
    table: RowTable,
    pair: FoldPair,
    *,
    scope: RuleScope,
    claim: RuleClaim,
    horizon_bars: int,
    features: Sequence[str],
    min_support: int = RULE_MIN_SUPPORT_DEFAULT,
    beam: int = RULE_MINER_BEAM,
    candidates_max: int = RULE_MINER_CANDIDATES_MAX,
) -> MinerResult:
    """Beam search over conjunctions of up to ``RULE_PREDICATES_MAX`` predicates on the **fit** fold.

    The search never touches the replicate fold: the miner draws and screens on ``pair.fit_ids`` and hands
    its survivors to the tester, which registers the family before reading a single replicate row. Rules
    are born at ``pair.registered_at_ms``, the fit fold's last bar, which is the bar the statement was
    drawn on and is a fold property rather than a wall clock.

    Returns every candidate whose support and market floors are met, best first, and the honest count of
    what was enumerated: ``n_candidates`` counts each distinct conjunction the search built, including the
    ones the floors dropped, because looking is what the FDR bar charges for.
    """
    thresholds: dict[str, tuple[int, ...]] = {}
    for feature in sorted(set(features)):
        ref = feature_ref(feature)
        values = _feature_values(table, feature, scope=scope, ids=pair.fit_ids)
        thresholds[feature] = tuple(
            value for value in quantiles_ppm(values) if ref.lo <= value <= ref.hi
        )
    usual = 0
    if claim.kind == "volatility":
        usual = usual_bp_for(table, scope, horizon_bars=horizon_bars, ids=pair.fit_ids)

    seen: set[tuple[tuple[str, str, int], ...]] = set()
    enumerated = 0
    truncated = False
    beam_conditions: list[tuple[Predicate, ...]] = [()]
    scored: dict[tuple[tuple[str, str, int], ...], MinedCandidate] = {}

    for _depth in range(RULE_PREDICATES_MAX):
        grown: list[MinedCandidate] = []
        for base in beam_conditions:
            used = {predicate.feature for predicate in base}
            for feature in sorted(thresholds):
                if feature in used:
                    continue
                for op in MINER_OPS:
                    for threshold in thresholds[feature]:
                        condition = tuple(
                            sorted(
                                (*base, Predicate(feature=feature, op=op, value=threshold)),
                                key=lambda predicate: predicate.sort_key,
                            )
                        )
                        key = tuple(predicate.sort_key for predicate in condition)
                        if key in seen:
                            continue
                        seen.add(key)
                        if enumerated >= candidates_max:
                            truncated = True
                            break
                        enumerated += 1
                        rule = make_rule(
                            author_kind="miner",
                            author_id=MINER_AUTHOR_ID,
                            born_at_ms=pair.registered_at_ms,
                            scope=scope,
                            condition=condition,
                            claim=claim,
                            horizon_bars=horizon_bars,
                            min_support=min_support,
                        )
                        rows = scope_rows(table, rule, ids=pair.fit_ids, usual_bp=usual)
                        lift_bp, support, n_markets = _score(rows)
                        candidate = MinedCandidate(
                            rule=rule, lift_bp=lift_bp, support=support, n_markets=n_markets
                        )
                        grown.append(candidate)
                        if support >= min_support and n_markets >= RULE_MIN_MARKETS and lift_bp > 0:
                            scored[key] = candidate
                    if truncated:
                        break
                if truncated:
                    break
            if truncated:
                break
        if not grown:
            break
        grown.sort(key=lambda candidate: candidate.order_key)
        beam_conditions = [candidate.rule.condition for candidate in grown[:beam]]
        if truncated:
            break

    ranked = sorted(scored.values(), key=lambda candidate: candidate.order_key)
    return MinerResult(
        template=template_of(scope, features, claim, horizon_bars),
        candidates=tuple(ranked),
        n_candidates=enumerated,
        truncated=truncated,
    )
