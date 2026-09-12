"""The rule record: predicates, scope, claim, the content-addressed id and the belief shift.

CONTRACTS_V2 18.2, package S2. A rule is a **statement**, not a function: a scope of categorical facts, a
conjunction of one to three integer predicates over the sensor features of 18.1, a claim about what the
price does where the conjunction holds, a horizon and a support floor. Because it is data, the same rule
is testable on every fold, every grid and every provider, and two authors who state the same thing
produce one rule: ``rule_id`` is the sha256 of the statement and never of its author (18.2, and the
identifier table of 18.7).

Three refusals are worth naming, because they are what makes the record trustworthy rather than merely
typed:

* **Totality** (ruling R279). ``fires`` reads the blocks it is handed and nothing else. A rule whose
  predicate names a feature of a sensor the caller did not buy does **not** fire, and raises nothing;
  ``readable_by`` is the filter a hive view applies **first**, so an unreadable insight is never
  considered rather than silently counted as not firing. An agent that did not buy ``hn`` cannot be moved
  by a rule about Hacker News, and cannot be crashed by one either.
* **The direction is part of the arithmetic** (ruling R280, correcting R240). Every ``y_row`` behind a
  measured ``lift_bp`` is already multiplied by ``claim.direction``, and promotion requires a positive
  lower bound, so a promoted "the price is too high" rule has a **positive** lift. Adding that lift to a
  belief raises the probability, which is the opposite of what the rule says. :func:`rule_shift_bp` puts
  the direction back and drops ``volatility`` claims, which enter no belief at all.
* **Canonical form** (18.2). The condition is sorted by ``(feature, op, value)`` with no duplicate
  ``(feature, op)`` pair and every scope tuple is sorted and unique, because the id is the hash of the
  rendered statement: an unsorted twin would be a second id for one rule.

``RuleRefusedError`` belongs to ``pmx.errors`` (13.1, ruling R236; 18.8 has S2 add it there) and lives
there now. It is re-exported from this module because every raise site and every test names it through
here, which is what made the move a one-line import rather than a rename across two packages.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pmx.errors import RuleRefusedError
from pmx.journal import canonical_sha256
from pmx.rules.vocabulary import (
    RE_FEATURE,
    SensorBlockLike,
    feature_ref,
    is_feature,
    read_feature,
    sensors_for,
)
from pmx.types import BP_ONE, MarketMeta, clamp_ppm, clamp_price_bp, ppm_from_bp

__all__ = (
    "AUTHOR_KINDS",
    "CLAIM_KINDS",
    "PREDICATE_OPS",
    "RE_AUTHOR_ID",
    "RE_FAMILY_ID",
    "RE_RULE_ID",
    "RULE_MIN_MARKETS",
    "RULE_MIN_SUPPORT_DEFAULT",
    "RULE_PREDICATES_MAX",
    "SCOPE_KEYS",
    "Predicate",
    "Rule",
    "RuleClaim",
    "RuleRefusedError",
    "RuleScope",
    "make_rule",
    "rule_from_dict",
    "rule_id_of",
    "rule_shift_bp",
    "shifted_belief_ppm",
)

#: PRD v5 2.2: conjunctions of up to three predicates, every author alike.
RULE_PREDICATES_MAX = 3

#: The comparison operators a predicate may use (18.2).
PREDICATE_OPS: tuple[str, ...] = ("lt", "le", "gt", "ge", "eq", "ne")

#: The three things a rule may claim (18.2).
CLAIM_KINDS: tuple[str, ...] = ("bias", "drift", "volatility")

#: Who may author a rule (18.2, ruling R237): the miner, an agent, or a detector of 16.4.
AUTHOR_KINDS: tuple[str, ...] = ("agent", "detector", "miner")

#: Matched ``(market, bar)`` rows on the fit fold, a default the first build reports against (18.2).
RULE_MIN_SUPPORT_DEFAULT = 30

#: Distinct markets a claim must hold over, a default (18.2).
RULE_MIN_MARKETS = 5

#: The scope keys a family template may let vary (18.2's ``FamilyTemplate.scope_keys``).
SCOPE_KEYS: tuple[str, ...] = ("kinds", "providers", "categories", "tags", "cohorts")

#: 18.7's identifier formats. ``RE_FAMILY_ID`` is defined here, beside the rule id it travels with, and
#: re-exported by ``pmx.rules.tester`` under the name 18.7 gives it: one pattern, two access paths, so a
#: rule can refuse a malformed ``family_id`` without the record importing the tester.
RE_RULE_ID = re.compile(r"^ru-[0-9a-f]{16}$")
RE_FAMILY_ID = re.compile(r"^hf-[0-9a-f]{16}$")
RE_AUTHOR_ID = re.compile(
    r"^([a-z][a-z0-9_]{0,31}(-[0-9a-f]{8})?|miner|news_lead|divergence|logic|comparative|cross_domain)$"
)

#: ``rule.v1.json``'s bounds on the two magnitudes, so a claim cannot carry a number no unit can hold.
_MAGNITUDE_BP_MAX = 10_000
_FACTOR_PPM_MAX = 1_000_000_000
_HORIZON_BARS_MAX = 99_999


@dataclass(frozen=True, slots=True)
class Predicate:
    """One integer comparison over one sensor feature (18.2).

    ``value`` is in the feature's own unit and inside its ``[lo, hi]``: a predicate outside the bounds is
    refused rather than clamped, because a clamped threshold would silently become a different rule with
    the same id.
    """

    feature: str
    op: str
    value: int

    def __post_init__(self) -> None:
        if not RE_FEATURE.match(self.feature) or not is_feature(self.feature):
            raise RuleRefusedError(
                "a predicate names a feature outside the sensor catalogue",
                reason="bad_rule",
                feature=self.feature,
            )
        if self.op not in PREDICATE_OPS:
            raise RuleRefusedError(
                "a predicate names an operator outside PREDICATE_OPS",
                reason="bad_rule",
                feature=self.feature,
                op=self.op,
            )
        ref = feature_ref(self.feature)
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise RuleRefusedError(
                "a predicate value is not an integer", reason="bad_rule", feature=self.feature
            )
        if not ref.lo <= self.value <= ref.hi:
            raise RuleRefusedError(
                "a predicate value is outside the feature's bounds",
                reason="bad_rule",
                feature=self.feature,
                value=self.value,
                lo=ref.lo,
                hi=ref.hi,
            )

    @property
    def sensor(self) -> str:
        """The sensor whose block carries this predicate's feature."""
        return feature_ref(self.feature).sensor

    @property
    def sort_key(self) -> tuple[str, str, int]:
        """18.2's canonical order of a condition: ``(feature, op, value)``."""
        return (self.feature, self.op, self.value)

    def holds(self, observed: int) -> bool:
        """Does the comparison hold for this integer read of the feature?"""
        if self.op == "lt":
            return observed < self.value
        if self.op == "le":
            return observed <= self.value
        if self.op == "gt":
            return observed > self.value
        if self.op == "ge":
            return observed >= self.value
        if self.op == "eq":
            return observed == self.value
        return observed != self.value

    def to_dict(self) -> dict[str, object]:
        return {"feature": self.feature, "op": self.op, "value": self.value}


@dataclass(frozen=True, slots=True)
class RuleScope:
    """Where a rule claims to hold: five sorted tuples of categorical facts, ``()`` meaning "any" (18.2).

    ``cohorts`` carries the cohort ids of 18.5 (decision D-S7). A market's cohort is read off its
    ``MarketMeta.cohort_id``, which amendment C1c landed (18.8's deferral table, ruling R266) and which
    is derived from the four facets by the one keying rule of ``pmx.cohorts``. A meta of an untagged
    dataset, or of a market 18.5 places in no cohort (``platform-meta``, or ``other`` on a facet),
    carries ``None`` there and a scope naming a cohort does not match it, which is the safe direction: a
    rule cannot claim to hold somewhere the dataset cannot place.
    """

    kinds: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    cohorts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for key in SCOPE_KEYS:
            values: tuple[str, ...] = getattr(self, key)
            if tuple(sorted(set(values))) != tuple(values):
                raise RuleRefusedError(
                    "a scope tuple is not sorted and unique, so its rule would have two ids",
                    reason="bad_rule",
                    scope_key=key,
                    values=list(values),
                )

    def matches(self, meta: MarketMeta) -> bool:
        """Does ``meta`` sit inside this scope? An empty tuple is "any" and never narrows."""
        if self.kinds and meta.kind not in self.kinds:
            return False
        if self.providers and meta.provider not in self.providers:
            return False
        if self.categories and meta.category not in self.categories:
            return False
        if self.tags and not set(self.tags).issubset(set(meta.tags)):
            return False
        if self.cohorts:
            cohort = getattr(meta, "cohort_id", None)
            if not isinstance(cohort, str) or cohort not in self.cohorts:
                return False
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "kinds": list(self.kinds),
            "providers": list(self.providers),
            "categories": list(self.categories),
            "tags": list(self.tags),
            "cohorts": list(self.cohorts),
        }


@dataclass(frozen=True, slots=True)
class RuleClaim:
    """What the rule says happens where its condition holds (18.2).

    ``direction`` is ``-1`` or ``1`` on a ``bias`` or a ``drift`` ("the price is too high" is ``-1``) and
    ``0`` on a ``volatility``; ``magnitude_bp`` carries the size of a bias or a drift and ``factor_ppm``
    the excess of a volatility. The magnitude is displayed and recorded but is **not** what the tester
    tests: the sign is, and the magnitude is re-estimated on every fold as the interval's point.
    """

    kind: str
    direction: int
    magnitude_bp: int
    factor_ppm: int

    def __post_init__(self) -> None:
        if self.kind not in CLAIM_KINDS:
            raise RuleRefusedError("a claim names an unknown kind", reason="bad_rule", kind=self.kind)
        if self.kind == "volatility":
            if self.direction != 0 or self.magnitude_bp != 0:
                raise RuleRefusedError(
                    "a volatility claim carries no direction and no magnitude",
                    reason="bad_rule",
                    direction=self.direction,
                    magnitude_bp=self.magnitude_bp,
                )
            if not 1 <= self.factor_ppm <= _FACTOR_PPM_MAX:
                raise RuleRefusedError(
                    "a volatility claim needs a factor in ppm", reason="bad_rule", factor_ppm=self.factor_ppm
                )
            return
        if self.direction not in (-1, 1):
            raise RuleRefusedError(
                "a bias or drift claim needs a direction of -1 or 1",
                reason="bad_rule",
                kind=self.kind,
                direction=self.direction,
            )
        if not 1 <= self.magnitude_bp <= _MAGNITUDE_BP_MAX:
            raise RuleRefusedError(
                "a bias or drift claim needs a magnitude in bp",
                reason="bad_rule",
                kind=self.kind,
                magnitude_bp=self.magnitude_bp,
            )
        if self.factor_ppm != 0:
            raise RuleRefusedError(
                "a bias or drift claim carries no volatility factor",
                reason="bad_rule",
                kind=self.kind,
                factor_ppm=self.factor_ppm,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "direction": self.direction,
            "magnitude_bp": self.magnitude_bp,
            "factor_ppm": self.factor_ppm,
        }


def rule_id_of(
    scope: RuleScope, condition: Sequence[Predicate], claim: RuleClaim, horizon_bars: int, min_support: int
) -> str:
    """18.2's content address: ``"ru-" + sha256(canonical_json([scope, condition, claim, h, support]))[:16]``.

    The author is deliberately not in it. Two authors proposing the same statement produce one rule, whose
    ``author_id`` is the first proposal's in journal order and whose ledger row counts ``n_proposals``.
    """
    payload = [
        scope.to_dict(),
        [predicate.to_dict() for predicate in condition],
        claim.to_dict(),
        horizon_bars,
        min_support,
    ]
    return "ru-" + canonical_sha256(payload)[:16]


@dataclass(frozen=True, slots=True)
class Rule:
    """A testable statement in the closed vocabulary (18.2, ``rule.v1.json``)."""

    rule_id: str
    author_kind: str
    author_id: str
    born_at_ms: int
    scope: RuleScope
    condition: tuple[Predicate, ...]
    claim: RuleClaim
    horizon_bars: int
    min_support: int
    family_id: str | None = None

    def __post_init__(self) -> None:
        if self.author_kind not in AUTHOR_KINDS:
            raise RuleRefusedError(
                "an unknown author kind", reason="bad_rule", author_kind=self.author_kind
            )
        if not RE_AUTHOR_ID.match(self.author_id):
            raise RuleRefusedError("a malformed author id", reason="bad_rule", author_id=self.author_id)
        if self.born_at_ms < 0:
            raise RuleRefusedError("born_at_ms is a bar open", reason="bad_rule", born_at_ms=self.born_at_ms)
        if not 1 <= len(self.condition) <= RULE_PREDICATES_MAX:
            raise RuleRefusedError(
                "a condition is one to RULE_PREDICATES_MAX predicates",
                reason="bad_rule",
                n_predicates=len(self.condition),
                maximum=RULE_PREDICATES_MAX,
            )
        keys = [predicate.sort_key for predicate in self.condition]
        if keys != sorted(keys):
            raise RuleRefusedError(
                "a condition is sorted by (feature, op, value)", reason="bad_rule", condition=keys
            )
        pairs = [(predicate.feature, predicate.op) for predicate in self.condition]
        if len(set(pairs)) != len(pairs):
            raise RuleRefusedError(
                "a condition carries a duplicate (feature, op) pair", reason="bad_rule", condition=pairs
            )
        if not 0 <= self.horizon_bars <= _HORIZON_BARS_MAX:
            raise RuleRefusedError(
                "a horizon is a bar count", reason="bad_rule", horizon_bars=self.horizon_bars
            )
        if self.claim.kind == "bias" and self.horizon_bars != 0:
            raise RuleRefusedError(
                "a bias is measured at resolution, so its horizon is 0",
                reason="bad_rule",
                horizon_bars=self.horizon_bars,
            )
        if self.claim.kind != "bias" and self.horizon_bars < 1:
            raise RuleRefusedError(
                "a drift or a volatility claim needs a horizon of at least one bar",
                reason="bad_rule",
                kind=self.claim.kind,
                horizon_bars=self.horizon_bars,
            )
        if self.min_support < RULE_MIN_SUPPORT_DEFAULT:
            raise RuleRefusedError(
                "min_support is at least RULE_MIN_SUPPORT_DEFAULT",
                reason="bad_rule",
                min_support=self.min_support,
                floor=RULE_MIN_SUPPORT_DEFAULT,
            )
        if self.family_id is not None and not RE_FAMILY_ID.match(self.family_id):
            raise RuleRefusedError("a malformed family id", reason="bad_rule", family_id=self.family_id)
        expected = rule_id_of(self.scope, self.condition, self.claim, self.horizon_bars, self.min_support)
        if self.rule_id != expected:
            raise RuleRefusedError(
                "the rule id is not the hash of the statement",
                reason="bad_rule",
                rule_id=self.rule_id,
                expected=expected,
            )

    @property
    def required_sensors(self) -> tuple[str, ...]:
        """The sorted sensors a diet must carry to read this rule (ruling R279)."""
        return sensors_for(predicate.feature for predicate in self.condition)

    def readable_by(self, sensors: Sequence[str]) -> bool:
        """Can a diet of ``sensors`` read every predicate of this rule?

        The filter the hive view (10.4) and the ``rules`` step (18.4) apply **before** evaluation, so an
        unreadable insight is never considered rather than silently counted as not firing.
        """
        bought = set(sensors)
        return all(sensor in bought for sensor in self.required_sensors)

    def condition_holds(self, blocks: Mapping[str, SensorBlockLike]) -> bool:
        """Does every predicate hold on ``blocks``, the scope set aside?

        The half of :meth:`fires` a **transfer test** needs (18.2 step 8): a re-test outside the rule's own
        scope asks what the condition does there, and asking ``fires`` would answer "no" for the one
        reason the test is not interested in. Total in the same way: an absent sensor is a no.
        """
        for predicate in self.condition:
            observed = read_feature(predicate.feature, blocks)
            if observed is None or not predicate.holds(observed):
                return False
        return True

    def fires(self, blocks: Mapping[str, SensorBlockLike], meta: MarketMeta) -> bool:
        """Does the scope hold on ``meta`` and every predicate on ``blocks``?

        Total by construction (ruling R279): a predicate whose sensor is absent from ``blocks`` makes the
        rule not fire, and nothing raises. A missing **input** is a different thing and never reaches
        here: it took the catalogue's sentinel when the block was sensed.
        """
        return self.scope.matches(meta) and self.condition_holds(blocks)

    def to_dict(self) -> dict[str, object]:
        """``rule.v1.json``'s payload, which is also what the hash of the id is taken over."""
        return {
            "rule_id": self.rule_id,
            "author_kind": self.author_kind,
            "author_id": self.author_id,
            "born_at_ms": self.born_at_ms,
            "scope": self.scope.to_dict(),
            "condition": [predicate.to_dict() for predicate in self.condition],
            "claim": self.claim.to_dict(),
            "horizon_bars": self.horizon_bars,
            "min_support": self.min_support,
            "family_id": self.family_id,
        }


def make_rule(
    *,
    author_kind: str,
    author_id: str,
    born_at_ms: int,
    scope: RuleScope,
    condition: Sequence[Predicate],
    claim: RuleClaim,
    horizon_bars: int,
    min_support: int = RULE_MIN_SUPPORT_DEFAULT,
    family_id: str | None = None,
) -> Rule:
    """Build a rule, sorting the condition and computing the id, so no author hashes by hand."""
    ordered = tuple(sorted(condition, key=lambda predicate: predicate.sort_key))
    return Rule(
        rule_id=rule_id_of(scope, ordered, claim, horizon_bars, min_support),
        author_kind=author_kind,
        author_id=author_id,
        born_at_ms=born_at_ms,
        scope=scope,
        condition=ordered,
        claim=claim,
        horizon_bars=horizon_bars,
        min_support=min_support,
        family_id=family_id,
    )


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise RuleRefusedError("a scope key is not a list", reason="bad_rule", scope_key=field)
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RuleRefusedError("a scope value is not a string", reason="bad_rule", scope_key=field)
        out.append(item)
    return tuple(out)


def _int_field(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuleRefusedError("a field is not an integer", reason="bad_rule", field=field, value=value)
    return value


def _str_field(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise RuleRefusedError("a field is not a string", reason="bad_rule", field=field, value=value)
    return value


def rule_from_dict(payload: Mapping[str, object]) -> Rule:
    """Validate one ``rule.v1.json`` payload into a :class:`Rule` (18.2, ruling R236).

    ``genome_from_dict``'s neighbour: the one door a proposal from an agent, a detector or a ledger line
    comes through, and every refusal is a ``RuleRefusedError`` naming its reason, never a ``KeyError`` a
    caller has to guess at.
    """
    scope_payload = payload.get("scope")
    if not isinstance(scope_payload, Mapping):
        raise RuleRefusedError("a rule carries no scope object", reason="bad_rule")
    unknown = set(scope_payload) - set(SCOPE_KEYS)
    if unknown:
        raise RuleRefusedError("a scope carries an unknown key", reason="bad_rule", keys=sorted(unknown))
    scope = RuleScope(
        kinds=_string_tuple(scope_payload.get("kinds", ()), field="kinds"),
        providers=_string_tuple(scope_payload.get("providers", ()), field="providers"),
        categories=_string_tuple(scope_payload.get("categories", ()), field="categories"),
        tags=_string_tuple(scope_payload.get("tags", ()), field="tags"),
        cohorts=_string_tuple(scope_payload.get("cohorts", ()), field="cohorts"),
    )
    condition_payload = payload.get("condition")
    if not isinstance(condition_payload, list | tuple):
        raise RuleRefusedError("a rule carries no condition list", reason="bad_rule")
    condition: list[Predicate] = []
    for entry in condition_payload:
        if not isinstance(entry, Mapping):
            raise RuleRefusedError("a predicate is not an object", reason="bad_rule")
        condition.append(
            Predicate(
                feature=_str_field(entry, "feature"), op=_str_field(entry, "op"), value=_int_field(entry, "value")
            )
        )
    claim_payload = payload.get("claim")
    if not isinstance(claim_payload, Mapping):
        raise RuleRefusedError("a rule carries no claim object", reason="bad_rule")
    claim = RuleClaim(
        kind=_str_field(claim_payload, "kind"),
        direction=_int_field(claim_payload, "direction"),
        magnitude_bp=_int_field(claim_payload, "magnitude_bp"),
        factor_ppm=_int_field(claim_payload, "factor_ppm"),
    )
    family = payload.get("family_id")
    if family is not None and not isinstance(family, str):
        raise RuleRefusedError("a family id is a string or null", reason="bad_rule", family_id=family)
    rule = Rule(
        rule_id=_str_field(payload, "rule_id"),
        author_kind=_str_field(payload, "author_kind"),
        author_id=_str_field(payload, "author_id"),
        born_at_ms=_int_field(payload, "born_at_ms"),
        scope=scope,
        condition=tuple(condition),
        claim=claim,
        horizon_bars=_int_field(payload, "horizon_bars"),
        min_support=_int_field(payload, "min_support"),
        family_id=family,
    )
    if not RE_RULE_ID.match(rule.rule_id):
        raise RuleRefusedError("a malformed rule id", reason="bad_rule", rule_id=rule.rule_id)
    return rule


def rule_shift_bp(insights: Sequence[tuple[RuleClaim, int]], *, weight_permille: int) -> int:
    """The belief shift in bp of the firing insights (ruling R280, correcting ruling R240).

    ``insights`` pairs each firing insight's claim with its measured ``lift_bp`` (the interval's point over
    ``y_row``). The shift is
    ``sum(claim.direction * (lift_bp * weight_permille // 1_000))`` over the ``bias`` and ``drift`` claims
    only, and the first version of the formula, ``sum(lift_bp * weight_permille // 1_000)``, is wrong in
    two ways that a test must be able to tell apart: every ``y_row`` is already multiplied by
    ``direction`` and promotion needs a positive lower bound, so a promoted ``direction = -1`` rule ("the
    price is too high") carries a **positive** lift and moved the belief **up**; and an unsigned
    ``volatility`` excess, which is not a statement about where the price goes at all, was added to a
    price.

    The direction multiplies the **rounded** magnitude, so a down-rule and its mirror shift by equal
    amounts. Rounding the signed product instead would floor a negative one unit further away and make the
    two asymmetric by construction.
    """
    total = 0
    for claim, lift_bp in insights:
        if claim.kind not in ("bias", "drift"):
            continue
        total += claim.direction * (lift_bp * weight_permille // 1_000)
    return total


def shifted_belief_ppm(last_price_bp: int, shift_bp: int) -> int:
    """``ppm_from_bp(last + shift)``, clamped: the belief a shifted price states (ruling R240).

    The clamp is the price clamp and then the probability clamp, so a shift that would push a belief past
    a certainty lands on the boundary the rest of the engine already uses rather than on an out-of-range
    ppm nobody validates.
    """
    return clamp_ppm(ppm_from_bp(clamp_price_bp(last_price_bp + shift_bp)))


def outcome_bp(resolution: int) -> int:
    """``BP_ONE * resolution``: the payout of a resolved binary in bp, which a bias claim measures against."""
    return BP_ONE * resolution
