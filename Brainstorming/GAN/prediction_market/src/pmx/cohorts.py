"""The cohort: the unit of comparative analysis (CONTRACTS_V2 18.5, decision D-S7, ruling R266).

A cohort groups the markets a comparison can be made *within*: same venue, same category, same primary
subject, same question shape, same horizon. It exists because ``tags`` was a raw dump of provider labels
(201 distinct values over 287 markets, ``docs/REVIEW_2026-09-09_SCALE_TAGS.md``) and a field like that
cannot group markets for a comparison.

Three things about a cohort are easy to get wrong and are pinned here:

* **A cohort has no fold of its own** (ruling R293). Unlike an ``EventCluster`` or a Kalshi ``event_key``
  group, which really are moved into one fold by the cut of 7.7, every market of a cohort keeps the fold
  7.7 gave it and ``n_train``, ``n_validation`` and ``n_sealed`` are what those folds left. The earlier
  wording "a cohort never crosses a fold" was deleted as stale: read as the cluster rule it would pull
  every market of a dense Kalshi series into one fold and collapse the train fold onto the sealed one,
  which is the opposite of what a cohort is for. The three per-fold counts in :class:`Cohort` exist
  **because** a cohort spans the folds.
* **A market belongs to exactly one cohort**, keyed on its ``provider``, ``category``, *primary* subject
  (``subject[0]``, the tagger's precedence order of 7.14), ``structure`` and ``horizon``. A market whose
  subject is ``platform-meta``, or whose ``structure`` or ``horizon`` is ``other``, belongs to **no**
  cohort: a self-referential Manifold market is not a forecast of the world, and a facet nothing decided
  is not a group.
* **There is no per-cohort claim** (ruling R283). A cohort statement is a row of the one claim, made on
  the one sealed read that claim already paid for. A per-cohort sealed read would be a second bite at the
  same sealed markets and would let a genome cherry-pick the cohort that cleared, so no ``--cohort`` flag,
  no ``cohort_id`` in a claim body and none in ``claims/access.jsonl`` exist. This module deliberately
  offers no "claim this cohort" door; it offers :func:`cohort_or_refuse`, which refuses.

Nothing here imports ``pmx.gateway`` or ``pmx.llm`` and nothing opens a socket (architecture rule 12,
ruling R245): a tag decides which cohort a market lands in, so a cohort a model wrote would move a claim
between two rebuilds.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from pmx.errors import CohortRefusedError

__all__ = [
    "COHORT_ID_MAX_CHARS",
    "COHORT_MIN_TRAIN",
    "COHORT_SIZE_BUCKETS",
    "FOLDS",
    "FOLD_SEALED",
    "FOLD_TRAIN",
    "FOLD_VALIDATION",
    "RE_COHORT_ID",
    "SUBJECT_PLATFORM_META",
    "VALUE_OTHER",
    "Cohort",
    "CohortMeta",
    "cohort_id_for_meta",
    "cohort_id_of",
    "cohort_ids_by_market",
    "cohort_key_of",
    "cohort_or_refuse",
    "cohort_rows",
    "cohort_size_bucket",
    "cohort_size_histogram",
    "cohorts_per_provider",
    "facets_of",
    "list_cohorts",
    "usable_cohorts",
]

#: A cohort is usable at thirty markets in the **train** fold (decisions D-S6 and D-S7). Thirty is the
#: smallest train fold a paired bound is worth stating on; below it the interval is wider than the effect
#: anybody is looking for, and quoting one anyway is how a comparison becomes noise with a decimal point.
COHORT_MIN_TRAIN: Final = 30

#: ``co-<provider>-<category>-<subject>-<structure>-<horizon>`` (18.7). The five segments are lowercase
#: slugs, so the id is readable in a leaderboard row and in a rule's ``scope.cohorts`` without a lookup.
RE_COHORT_ID: Final = re.compile(r"^co-[a-z]+-[a-z]+-[a-z0-9-]+-[a-z-]+-[a-z-]+$")

#: The cap 18.7 puts on a cohort id, which ``dataset.v1.json`` and ``journal.v2.json`` both enforce.
COHORT_ID_MAX_CHARS: Final = 96

#: The three folds of 7.7, in cut order.
FOLD_TRAIN: Final = "train"
FOLD_VALIDATION: Final = "validation"
FOLD_SEALED: Final = "sealed"
FOLDS: Final = (FOLD_TRAIN, FOLD_VALIDATION, FOLD_SEALED)

#: The subject that names Manifold's self-referential markets and keeps them out of every forecast
#: cohort (7.14, ruling R273). It is a *subject* and not a filter, so the markets are counted and
#: reported rather than silently dropped into ``other``.
SUBJECT_PLATFORM_META: Final = "platform-meta"

#: The counted fallback of the ``structure`` and ``horizon`` facets. A market carrying it on either facet
#: belongs to no cohort: "the shape of this question is unknown" is not a group of questions.
VALUE_OTHER: Final = "other"

#: The buckets of ``manifest.taxonomy.cohort_size_histogram`` (7.8), in reading order.
COHORT_SIZE_BUCKETS: Final = ("1", "2-4", "5-9", "10-29", "30+")


@runtime_checkable
class CohortMeta(Protocol):
    """What :func:`list_cohorts` reads off a market's metadata, and nothing more.

    ``pmx.types.MarketMeta`` satisfies this. It is a protocol rather than the concrete class for one
    reason worth stating: the five taxonomy fields of ``MarketMeta`` (``subject``, ``structure``,
    ``horizon``, ``provider_labels``, ``cohort_id``) are 18.8's deferral row for ``src/pmx/types.py``,
    which names DS1 as the package that applies them, and this module may not edit another package's
    file. So the four fields that exist today are declared here and the facets are read through
    :func:`facets_of`, which answers the untagged default for a meta that does not carry them yet. The
    day the five defaulted fields land, ``facets_of`` reads them and nothing else changes: a dataset
    built before the taxonomy has no cohorts, which is exactly what 7.2 says ``Dataset.cohorts`` is on
    one (``()``).
    """

    @property
    def id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def category(self) -> str: ...

    @property
    def fold(self) -> str: ...


def facets_of(meta: CohortMeta) -> tuple[tuple[str, ...], str, str]:
    """``(subject, structure, horizon)`` of a meta, and ``((), "", "")`` on an untagged one.

    A dataset built before 7.14's taxonomy carries no facet, and 7.2 defaults all five fields for that
    case rather than making an old dataset unloadable. The read is therefore tolerant of a field being
    absent and **not** of it being wrong: a value that is present and not a string is a build defect and
    is read as untagged, so it lands in no cohort and is counted in the manifest's ``other`` bucket where
    a reviewer sees it.
    """
    raw_subject = getattr(meta, "subject", ())
    subject = (
        tuple(value for value in raw_subject if isinstance(value, str))
        if isinstance(raw_subject, tuple)
        else ()
    )
    raw_structure = getattr(meta, "structure", "")
    structure = raw_structure if isinstance(raw_structure, str) else ""
    raw_horizon = getattr(meta, "horizon", "")
    horizon = raw_horizon if isinstance(raw_horizon, str) else ""
    return subject, structure, horizon


def cohort_id_of(*, provider: str, category: str, subject: str, structure: str, horizon: str) -> str | None:
    """``co-<provider>-<category>-<subject>-<structure>-<horizon>``, or ``None`` for no cohort (18.5).

    ``None`` is the answer for a ``platform-meta`` subject, for an ``other`` value on **any** of the
    three facets, for an untagged market, and for any five-tuple whose rendered id would not match
    :data:`RE_COHORT_ID` or would overrun :data:`COHORT_ID_MAX_CHARS`.

    Two of those need their reason on the record. The last is not a formality: the id travels in
    ``market_listed`` (9.2, ruling R288) and in ``dataset.v1.json``, both of which validate it, so a
    facet value that cannot be spelled in an id must fail here rather than at seal time. And ``other``
    excludes on the **subject** facet as well as on the two 18.5 spells out: "a market whose subject is
    ``platform-meta`` or whose ``structure`` or ``horizon`` is ``other``" names the two facets that can
    be ``other`` beside a real subject, and a cohort keyed on ``subject = "other"`` would group a
    presidential summit with a papal encyclical and call the two comparable, which is the one thing a
    cohort must not do. Nothing is hidden by the exclusion: ``manifest.taxonomy.per_venue`` counts
    ``n_other_subject`` per venue (7.14, ruling R268), so the markets in no cohort are on the record.
    """
    if not subject or subject in (SUBJECT_PLATFORM_META, VALUE_OTHER):
        return None
    if not structure or structure == VALUE_OTHER:
        return None
    if not horizon or horizon == VALUE_OTHER:
        return None
    cohort_id = f"co-{provider}-{category}-{subject}-{structure}-{horizon}"
    if len(cohort_id) > COHORT_ID_MAX_CHARS or RE_COHORT_ID.fullmatch(cohort_id) is None:
        return None
    return cohort_id


def cohort_key_of(meta: CohortMeta) -> tuple[str, str, str, str, str] | None:
    """The five-tuple a market is keyed on, or ``None`` when it belongs to no cohort.

    The subject read is ``subject[0]`` and nothing else: the tagger emits its subjects in **precedence
    order** (7.14) and the first is the primary subject. A market with four subjects is one market in one
    cohort, not four rows of a table that would then count it four times in a comparison.
    """
    subject, structure, horizon = facets_of(meta)
    if not subject:
        return None
    primary = subject[0]
    if (
        cohort_id_of(
            provider=meta.provider,
            category=meta.category,
            subject=primary,
            structure=structure,
            horizon=horizon,
        )
        is None
    ):
        return None
    return meta.provider, meta.category, primary, structure, horizon


def cohort_id_for_meta(meta: CohortMeta) -> str | None:
    """``MarketMeta.cohort_id`` (7.2) and ``market_listed.cohort_id`` (9.2, ruling R288).

    The one implementation of the keying rule, exclusions included. The projection reads the id off the
    journal instead of calling this a second time, which is what ruling R288 added the journal field for.
    """
    key = cohort_key_of(meta)
    if key is None:
        return None
    provider, category, subject, structure, horizon = key
    return cohort_id_of(
        provider=provider, category=category, subject=subject, structure=structure, horizon=horizon
    )


@dataclass(frozen=True, slots=True)
class Cohort:
    """One cohort with its per-fold counts (18.5).

    ``usable`` is the leaderboard bar (``n_train >= COHORT_MIN_TRAIN``, 12.10) and
    ``usable_for_paired_test`` is the analysis bar (decision D-S13): usable **and** no empty fold. The
    two are separate because a cohort can clear the first and fail the second, which is the defect
    decision D-S13 was written from: all six cohorts that reached ten markets on the prototype sat
    entirely inside one fold, a consequence of the inverted split the fold fix of D-R1 repaired.

    ``market_ids`` lives on the object and **never** in the manifest row: the row is a count, and a
    manifest that listed the ids of every cohort would restate the whole market index once per facet
    combination.
    """

    cohort_id: str
    category: str
    subject: str
    structure: str
    horizon: str
    provider: str
    n_train: int
    n_validation: int
    n_sealed: int
    usable: bool
    usable_for_paired_test: bool
    market_ids: tuple[str, ...]

    @property
    def n(self) -> int:
        """The whole cohort, which is the number ``per_cohort`` reports beside every bound (18.5)."""
        return self.n_train + self.n_validation + self.n_sealed

    def to_dict(self) -> dict[str, object]:
        """The manifest row of 7.8: every field but ``market_ids``, in ``dataset.v1.json``'s key order."""
        return {
            "cohort_id": self.cohort_id,
            "category": self.category,
            "subject": self.subject,
            "structure": self.structure,
            "horizon": self.horizon,
            "provider": self.provider,
            "n_train": self.n_train,
            "n_validation": self.n_validation,
            "n_sealed": self.n_sealed,
            "usable": self.usable,
            "usable_for_paired_test": self.usable_for_paired_test,
        }


def _cohort_of(key: tuple[str, str, str, str, str], members: Sequence[tuple[str, str]]) -> Cohort:
    """Build one cohort from its ``(market_id, fold)`` members; the caller owns the grouping."""
    provider, category, subject, structure, horizon = key
    cohort_id = cohort_id_of(
        provider=provider, category=category, subject=subject, structure=structure, horizon=horizon
    )
    if cohort_id is None:  # pragma: no cover - the caller filtered on exactly this
        raise CohortRefusedError(
            "a cohort key that yields no cohort id reached the cohort constructor",
            provider=provider,
            category=category,
            subject=subject,
            structure=structure,
            horizon=horizon,
        )
    counts = dict.fromkeys(FOLDS, 0)
    for _market_id, fold in members:
        if fold in counts:
            counts[fold] += 1
    n_train = counts[FOLD_TRAIN]
    usable = n_train >= COHORT_MIN_TRAIN
    return Cohort(
        cohort_id=cohort_id,
        category=category,
        subject=subject,
        structure=structure,
        horizon=horizon,
        provider=provider,
        n_train=n_train,
        n_validation=counts[FOLD_VALIDATION],
        n_sealed=counts[FOLD_SEALED],
        usable=usable,
        usable_for_paired_test=(
            usable and n_train > 0 and counts[FOLD_VALIDATION] > 0 and counts[FOLD_SEALED] > 0
        ),
        market_ids=tuple(sorted(market_id for market_id, _fold in members)),
    )


def list_cohorts(metas: Iterable[CohortMeta]) -> tuple[Cohort, ...]:
    """Every cohort of a dataset, sorted by ``cohort_id`` (18.5).

    The **one** implementation: the builder calls it for ``manifest.cohorts`` and the loader calls it for
    ``Dataset.cohorts``, so a cohort row on disk and a cohort object in memory can never disagree about
    the keying rule or about which markets it excludes. ``()`` on a dataset built before the taxonomy,
    because no market carries a facet and no facet means no group.

    A market counted in no cohort is not lost: ``manifest.taxonomy.per_venue`` counts the ``other`` and
    ``platform-meta`` markets per venue (7.14, ruling R268), so the difference between the market count
    and the cohorts' total is always readable off the manifest.
    """
    grouped: dict[tuple[str, str, str, str, str], list[tuple[str, str]]] = {}
    for meta in metas:
        key = cohort_key_of(meta)
        if key is None:
            continue
        grouped.setdefault(key, []).append((meta.id, meta.fold))
    cohorts = tuple(_cohort_of(key, members) for key, members in grouped.items())
    return tuple(sorted(cohorts, key=lambda cohort: cohort.cohort_id))


def cohort_or_refuse(cohorts: Iterable[Cohort], cohort_id: str) -> Cohort:
    """The cohort under ``cohort_id``, or :class:`~pmx.errors.CohortRefusedError` (18.5, ruling R283).

    Three refusals, all before any measurement: the id names no cohort of this dataset, the cohort's
    train fold is below :data:`COHORT_MIN_TRAIN`, or one of its three folds is empty so no paired bound
    and no replication exist for it. The bar is never weakened to a smaller one, because a bound quoted
    on twelve markets is not a weaker claim than a bound on thirty: it is a claim about a different and
    unmeasured thing.

    The refusal is what a caller asking for a measurement gets. A *report* of every cohort, the unusable
    ones included with ``verdict: "not_usable"`` and their counts, is the ``per_cohort`` table of a claim
    (12.8), which is why 18.5 asks for both: the reader must see that the cohort was measured and why
    nothing was concluded from it.
    """
    by_id = {cohort.cohort_id: cohort for cohort in cohorts}
    cohort = by_id.get(cohort_id)
    if cohort is None:
        raise CohortRefusedError(
            "no cohort of this dataset carries that id", cohort_id=cohort_id, n_cohorts=len(by_id)
        )
    if not cohort.usable:
        raise CohortRefusedError(
            "a cohort below the minimum train fold carries no measurement",
            cohort_id=cohort_id,
            n_train=cohort.n_train,
            minimum=COHORT_MIN_TRAIN,
        )
    if not cohort.usable_for_paired_test:
        raise CohortRefusedError(
            "a cohort with an empty fold carries no paired test",
            cohort_id=cohort_id,
            n_train=cohort.n_train,
            n_validation=cohort.n_validation,
            n_sealed=cohort.n_sealed,
        )
    return cohort


def usable_cohorts(cohorts: Iterable[Cohort]) -> tuple[Cohort, ...]:
    """The cohorts a leaderboard emits a row for (``n_train >= COHORT_MIN_TRAIN``, 12.10)."""
    return tuple(cohort for cohort in cohorts if cohort.usable)


def cohorts_per_provider(cohorts: Iterable[Cohort]) -> dict[str, int]:
    """``{provider: n_usable_cohorts}``, which is what ``build_outcome`` weighs against the venue target.

    The count is of **usable** cohorts, because that is what decision D-S11's targets are stated in (40
    on Kalshi, 8 on Manifold): a venue with two hundred cohorts of one market has no comparison in it.
    """
    counts: dict[str, int] = {}
    for cohort in cohorts:
        if cohort.usable:
            counts[cohort.provider] = counts.get(cohort.provider, 0) + 1
    return dict(sorted(counts.items()))


def cohort_size_bucket(n: int) -> str:
    """Which bucket of :data:`COHORT_SIZE_BUCKETS` a cohort of ``n`` markets falls in (7.8)."""
    if n <= 1:
        return COHORT_SIZE_BUCKETS[0]
    if n <= 4:
        return COHORT_SIZE_BUCKETS[1]
    if n <= 9:
        return COHORT_SIZE_BUCKETS[2]
    if n <= 29:
        return COHORT_SIZE_BUCKETS[3]
    return COHORT_SIZE_BUCKETS[4]


def cohort_size_histogram(cohorts: Iterable[Cohort]) -> dict[str, int]:
    """``manifest.taxonomy.cohort_size_histogram`` (7.8): every bucket present, zeros included.

    A histogram that omits its empty buckets reads as a histogram whose buckets were chosen after the
    fact, and the shape of this one is the headline measurement of decision D-S12: 58 cohorts of size 1
    and zero of size 30 or more over the 287 markets of the first build.
    """
    counts: dict[str, int] = dict.fromkeys(COHORT_SIZE_BUCKETS, 0)
    for cohort in cohorts:
        counts[cohort_size_bucket(cohort.n)] += 1
    return counts


def cohort_rows(cohorts: Iterable[Cohort]) -> list[dict[str, object]]:
    """``manifest.cohorts`` (7.8): one row per cohort, sorted by ``cohort_id``, without ``market_ids``."""
    return [cohort.to_dict() for cohort in sorted(cohorts, key=lambda cohort: cohort.cohort_id)]


def cohort_ids_by_market(cohorts: Iterable[Cohort]) -> Mapping[str, str]:
    """``{market_id: cohort_id}`` over the cohorts given, for the journal's ``market_listed`` field.

    Every market appears at most once by construction (a market belongs to exactly one cohort), and a
    market of no cohort is simply absent, which the caller reads as ``None``.
    """
    rows: dict[str, str] = {}
    for cohort in cohorts:
        for market_id in cohort.market_ids:
            rows[market_id] = cohort.cohort_id
    return dict(sorted(rows.items()))
