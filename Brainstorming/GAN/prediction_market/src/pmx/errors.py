"""The one error taxonomy of pmx v2 (CONTRACTS_V2 section 13.1).

Every failure in pmx is one of these, and each one names the boundary it was raised at, because a
deterministic arena is only auditable if a refusal is as specific as a result. ``PmxError`` carries
context as keyword arguments instead of interpolating them into prose: the message stays greppable, the
context stays machine readable, and ``str()`` renders both in a stable, sorted order so a test can pin an
error the way it pins a number.

Engine code never catches ``PmxError`` broadly. The gateway is the one exception and only to build a
fallback reply (section 13.1), which is why the impure-edge errors (``ProviderError``,
``MalformedResponseError``, ``BudgetExceededError``, ``GatewayError``) are siblings rather than a private
hierarchy: the gateway maps them to a ``RejectReason`` and the run continues, while a ``LeakError`` or a
``DatasetHashMismatchError`` must always reach the caller and stop the run.
"""

from __future__ import annotations


class PmxError(Exception):
    """Base of every pmx error: a message plus sorted ``key=value`` context.

    The context is kept as a mapping rather than baked into the message so that a caller can read
    ``err.context["market_id"]`` instead of parsing prose, and so that two errors that differ only in
    context still compare equal by message.
    """

    __slots__ = ("context", "message")

    def __init__(self, message: str, **context: object) -> None:
        self.message = message
        self.context: dict[str, object] = dict(context)
        super().__init__(message)

    def __str__(self) -> str:
        if not self.context:
            return self.message
        rendered = " ".join(f"{key}={self.context[key]!r}" for key in sorted(self.context))
        return f"{self.message} {rendered}"

    def __repr__(self) -> str:
        rendered = "".join(f", {key}={self.context[key]!r}" for key in sorted(self.context))
        return f"{type(self).__name__}({self.message!r}{rendered})"


class SchemaError(PmxError):
    """A file or a payload fails its JSON schema, its pydantic model or a structural rule of the
    contract that the schema cannot express (bar density, trade order, the news day key)."""


class LeakError(PmxError):
    """An instant after the freeze, or a future item reaching a view.

    Raised by the builder (a market resolving at or after ``freeze_ms``, a news item published after it)
    and by the observation builder (a bar, trade, news item, hive entry or memory record that the as-of
    rules of section 5.4 forbid at ``now_ms``).
    """


class SealError(PmxError):
    """``seal_dataset`` met a ``reconstructed`` market: a reconstructed tape is never claimable."""


class DatasetHashMismatchError(PmxError):
    """A recomputed digest differs from the manifest, so the dataset on disk is not the one that was
    sealed. ``run_backtest`` raises this before reading a single market."""


class UnknownSubstreamError(PmxError):
    """An unregistered RNG substream name (``pmx.rng``, section 6.3): new randomness needs a new
    registered name in the same commit."""


class NonCanonicalValueError(PmxError):
    """``canonical_json`` or a journal reader met a float, a set, bytes, a carriage return or another
    type the one encoder refuses (section 4.1)."""


class JournalError(PmxError):
    """A journal invariant broke: a ``seq`` gap, a foreign run id, a phase order breach, an append after
    close."""


class ObservationTooLargeError(PmxError):
    """The canonical size of an observation exceeds ``OBSERVATION_MAX_BYTES``. The builder raises rather
    than truncating silently, because a silent truncation is a leak of a different kind: two agents would
    see different worlds for the same bar."""


class FrozenMemoryError(PmxError):
    """A write reached a frozen memory (a claim run freezes memory before the first bar)."""


class MemoryFullError(PmxError):
    """A write would push the memory past ``MEMORY_MAX_BYTES`` and eviction could not make room."""


class FoldIntegrityError(PmxError):
    """The folds a manifest declares are not the folds the metas recompute (7.7, 18.5).

    Raised by ``verify_dataset``, ``load_dataset``, ``make_folds``, the rule tester and ``claim`` when
    the count-quantile cuts, the fold keys or the realised shares disagree with the recomputation, when a
    cluster or ``event_key`` group spans two folds, when a fold is empty, when ``Folds.rolling`` would
    hold no pair, or when a cohort row disagrees with the folds and facets recomputed (rulings R248,
    R266, R277, R290). It is its own class and not a ``SchemaError``: the file parsed, and what failed is
    an arithmetic a reader can redo.
    """


class ShowcaseDatasetError(PmxError):
    """A ``purpose: "showcase"`` dataset reached something only a research dataset may feed.

    A showcase dataset holds landmark events kept apart rather than thrown away (5.6, ruling R263): it
    seals, loads and replays like any other and ``run_backtest`` runs it, but it is never the source of a
    fold, a fitness value, a rule promotion, an insight or a claim, and ``make_folds``, ``run_generation``,
    ``evolve``, ``claim``, the rule tester and ``pmx.features.matrix`` each raise this before reading a
    market. ``run_backtest`` raises it too when ``memory_from_run_id`` or ``hive_from_run_id`` names a run
    that ran on one (8.1, ruling R291), because memory carried between runs is a channel into an
    observation. No flag lifts any of those refusals and none of them is a silent skip.
    """


class SensorAbsentError(PmxError):
    """An agent read a field its sensor set did not buy (18.1, ruling R232).

    Raised by the sensed views of the observation builder (``SensedMarketView``, ``SensedObservation``,
    ``SensedBar``, ``SensedHiveView``) and by nothing else, carrying ``field``, ``unsensed`` and ``view``.
    "The agent did not buy this" is a distinct failure from "a file failed its schema", which is what the
    hook raised for want of a better fit, and a test that pins one must not pass on the other.
    """


class CohortRefusedError(PmxError):
    """A cohort was asked for a measurement it cannot carry (18.5, rulings R266 and R283).

    Raised by ``pmx.cohorts.cohort_or_refuse``, by the per-cohort leaderboard of 12.10 and by the
    ``comparative`` detector when the cohort is unknown, when its train fold holds fewer than
    ``COHORT_MIN_TRAIN`` markets, or when it is not ``usable_for_paired_test`` because one of its three
    folds is empty. It fires **before** any measurement and is never weakened to a smaller bar: a paired
    bound on a cohort that lives in one fold is not a weaker statement, it is a different and false one.
    """


class RuleRefusedError(PmxError):
    """A rule, a proposal or a test the hypothesis layer refuses (13.1, ruling R236).

    ``reason`` names which refusal it is, and the ones the contract spells are ``bad_rule`` (the record
    does not validate), ``duplicate`` (the same content on the same fold pair, 18.2 step 4),
    ``family_too_large`` (``n_screened`` above what the permutation grid can resolve, ruling R282) and
    ``unregistered_family`` (a replicate read before the family was written down, 18.2 step 1).

    It lives here and not in ``pmx.rules.rule``, where it was first written, because 13.1 names this
    module for every error of the contract and 18.8's second row says so in as many words. A class with a
    contracted name living in a module the contract does not name is the defect the ``FoldIntegrityError``
    bridge was: ``pmx.rules.rule`` re-exports the name, so every raise site and every test that spells it
    through that module is unchanged.
    """


class ClaimRefusedError(PmxError):
    """A second claim on the same ``(dataset_hash, provider, genome_hash)``, or an earlier aborted peek
    at the sealed fold: an aborted peek is a used claim, not a free one (section 12.8)."""


class ProviderBlockedError(PmxError):
    """A provider answered with a block page (or a certificate) that is not the provider's: the ANJ
    block on Polymarket. Never retried, because retrying a legal block is pointless."""


class ProviderError(PmxError):
    """A provider failed in a way retrying could not fix, or failed after every retry."""


class MalformedResponseError(PmxError):
    """A provider answered something that is not what its documented shape says."""


class BudgetExceededError(PmxError):
    """An LLM call would exceed the run's USD or call budget (``BudgetTracker``, section 11.1)."""


class GatewayError(PmxError):
    """The gateway failed to obtain a usable reply: a timeout, a crash, an unparseable payload."""


class InvalidConfigError(PmxError):
    """A config value is outside its contracted cap. Raised by every config ``__post_init__``, so a bad
    run dies at construction rather than at bar 400."""


class NotConfiguredError(PmxError):
    """An optional path was used without its token or setting: the Metaculus importer without a token,
    a fetcher without ``PMX_USER_AGENT_CONTACT``, a live job without its provider key."""
