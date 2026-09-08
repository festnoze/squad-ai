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
