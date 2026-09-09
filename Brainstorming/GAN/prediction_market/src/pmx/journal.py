r"""The append-only event journal of pmx and the one canonical JSON encoder (CONTRACTS_V2 4 and 9).

This module is the only writer of ``runs/<run_id>/journal.jsonl`` and the only reader that turns
those bytes back into events. Everything else in the engine emits through :class:`Journal` and
never touches a file handle, which is what makes "``seq`` starts at 1 and increases by exactly 1"
a property of the type rather than a convention.

Why the module is safety critical
---------------------------------
The journal is the AC-3 artefact: two machines run the same ``(dataset_hash, roster, config,
seed)`` and compare ``journal_hash``, and ``pmx replay`` rebuilds ``results.json`` from the
journal alone. Those comparisons only mean something if the bytes on disk are exactly the
concatenation of ``canonical_json(event.to_dict()) + "\n"``, so:

1. every file is opened with ``encoding=JOURNAL_ENCODING`` and ``newline=JOURNAL_NEWLINE`` (that
   is ``"utf-8"`` and ``"\n"``). The default text mode of :func:`open` rewrites ``"\n"`` into
   ``"\r\n"`` on Windows, the development platform here, which would leave the in-memory hash
   right and the file wrong;
2. a line holding a carriage return is **rejected**, never normalised away, on the way in as
   well as on the way out: reading a CRLF file in universal-newline mode hands back clean
   ``"\n"`` lines, so the corruption would only surface once two machines compared files;
3. the line is built at append time, even for an in-memory journal, so a float, a wall clock or a
   provider metric fails at the emitting call site (section 4.4) instead of at the next flush.

What may never enter a journal (section 4.4): floats, wall-clock instants, durations, latencies,
provider costs, token counts, retry counts, the rationale text of an LLM reply, and the iteration
order of a ``set``. :func:`canonical_json` rejects the float structurally and
:meth:`Journal.emit` rejects the forbidden field names by name, with the message that says where
they belong instead (``llm_trace.jsonl``, which is outside every hash). A journal event may carry
the **outcome** of an LLM call, because the run replays from the journal without the provider:
what the model said is data, what it cost is not.

Ownership (section 9.3): this module appends whatever an emitter hands it and never invents an
event. ``seq`` is assigned here and nowhere else.

Note on the ``pmx.journal.events.*`` spelling of section 14: the event dataclasses are defined in
this one file, because section 13 gives D7 exactly ``src/pmx/rng.py`` and ``src/pmx/journal.py``.
They are exported from ``pmx.journal`` directly, and ``pmx.journal.events`` is registered as a
runtime alias module holding the same classes, so both spellings import at run time. Only the
direct one (``from pmx.journal import Filled``) is visible to a type checker.
"""

from __future__ import annotations

import hashlib
import json
import types as pytypes
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Literal,
    TextIO,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from jsonschema import Draft202012Validator

from pmx.data.schema import load_schema, validate_against_schema
from pmx.errors import JournalError, NonCanonicalValueError, SchemaError
from pmx.types import JOURNAL_ENCODING as JOURNAL_ENCODING
from pmx.types import JOURNAL_NEWLINE as JOURNAL_NEWLINE
from pmx.types import PHASE_ORDER

if TYPE_CHECKING:  # pragma: no cover - typing only, and jsonschema ships no strict stubs
    from typing import Any

__all__ = [
    "EVENT_CLASSES",
    "EVENT_TYPES",
    "FORBIDDEN_PAYLOAD_FIELDS",
    "JOURNAL_ENCODING",
    "JOURNAL_NEWLINE",
    "JOURNAL_SCHEMA",
    "ActionReceived",
    "ActionRejected",
    "AgentRuined",
    "BarClosed",
    "BarOpened",
    "CandidateScored",
    "CashEventApplied",
    "EquityMarked",
    "EvolutionEnded",
    "EvolutionStarted",
    "FeeCharged",
    "Filled",
    "ForecastRecorded",
    "ForecastResolved",
    "GenerationClosed",
    "GenerationStarted",
    "HiveWritten",
    "InstrumentClosed",
    "Journal",
    "JournalEvent",
    "MarketListed",
    "MarketPriced",
    "MemoryWritten",
    "ObservationBuilt",
    "OrderExpired",
    "OrderPlaced",
    "OrderRejected",
    "ReplyReceived",
    "ResearchSpent",
    "RunEnded",
    "RunStarted",
    "SealedTestOpened",
    "Settled",
    "SettlementApplied",
    "canonical_json",
    "canonical_sha256",
    "event_from_dict",
    "event_from_line",
    "event_to_line",
    "filter_events",
    "iter_bars",
    "iter_journal",
    "journal_hash",
    "journal_hash_from_lines",
    "journal_hash_of_file",
    "payload_field_names",
    "read_journal",
    "validate_event_dict",
    "verify_journal",
    "write_journal",
]

_JSON_SEPARATORS = (",", ":")

#: ``JOURNAL_ENCODING`` (UTF-8 without a BOM) and ``JOURNAL_NEWLINE`` are imported from ``pmx.types``
#: and re-exported here, which is the spelling section 14 lists against D7. They cannot be *declared*
#: here, because ``pmx.data.schema`` and ``pmx.data.loader`` need them and both sit below this module
#: in the import order (ruling R86). Passing the newline to ``open`` disables the platform translation,
#: so a journal written on Windows is byte identical to one written on Linux (section 4.2).
#: The schema every replayed event is validated against (section 7.13 resolves the path).
JOURNAL_SCHEMA: str = "journal.v2.json"

#: The bar phases, in order. A journal never mixes them with ``generation`` (section 9.1).
_BAR_PHASES: tuple[str, ...] = ("open", "observe", "decide", "execute", "settle", "learn", "hive", "close")

#: Payload field names that are refused at write time, whatever their value. Every one of them is
#: something that varies between two runs of the same seed (a wall clock, a duration, a provider
#: cost, a token count, a retry count) or free provider text; they belong in ``llm_trace.jsonl``,
#: which is deliberately outside every hash (section 4.4).
FORBIDDEN_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {
        "attempts",
        "cost",
        "duration",
        "elapsed",
        "finished_at",
        "latency",
        "model_text",
        "now_ms",
        "prompt_text",
        "rationale",
        "raw_text",
        "retries",
        "started_at",
        "timestamp",
        "tokens",
        "wall_clock",
        "wall_clock_ms",
        "wall_ms",
    }
)

#: Prefixes and suffixes of the same ban. No field name of the catalogue matches one of these, so
#: a match is always an emitter reaching for something the journal must not carry.
_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "cost_",
    "duration_",
    "elapsed_",
    "latency_",
    "retry_",
    "tokens_",
    "wall_",
    "wallclock_",
)
_FORBIDDEN_SUFFIXES: tuple[str, ...] = ("_usd", "_seconds", "_secs", "_latency", "_latency_ms", "_wall_ms")

E = TypeVar("E", bound="JournalEvent")


# --------------------------------------------------------------------------------------------------
# Canonical serialisation (section 4.1)
# --------------------------------------------------------------------------------------------------
def _encode(value: object, path: str) -> object:
    """Recursively convert ``value`` into the canonical JSON friendly form.

    Args:
        value: Any value found inside an event payload or a dataset file.
        path: Dotted path used in error messages, starting at ``"$"``.

    Returns:
        A structure made only of ``dict``, ``list``, ``str``, ``int``, ``bool`` and ``None``.

    Raises:
        NonCanonicalValueError: On a float, a set, ``bytes``, an :class:`~enum.Enum` that is not a
            ``str`` subclass, a non-string object key, or any other type.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        # A StrEnum renders as its value; any other Enum (IntEnum included) is refused, because
        # its rendering would depend on which member happens to be defined first.
        if isinstance(value, str):
            return str(value)
        raise NonCanonicalValueError(
            "only a str-subclass Enum may be serialised; give the payload the plain value",
            path=path,
            type=type(value).__name__,
        )
    if isinstance(value, bool | int):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        raise NonCanonicalValueError(
            "floats are forbidden; use a *_ppm, *_bp, *_cents, *_milli or *_micro integer",
            path=path,
            value=repr(value),
        )
    if isinstance(value, bytes | bytearray):
        raise NonCanonicalValueError("bytes have no canonical JSON form", path=path)
    if isinstance(value, set | frozenset):
        raise NonCanonicalValueError("sets have no stable order; pass a sorted tuple", path=path)
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        keys: list[str] = []
        for key in mapping:
            if not isinstance(key, str):
                raise NonCanonicalValueError("object keys must be strings", path=path, key=repr(key))
            keys.append(key)
        out: dict[str, object] = {}
        for key in sorted(keys):
            out[key] = _encode(mapping[key], f"{path}.{key}")
        return out
    if isinstance(value, list | tuple):
        return [_encode(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise NonCanonicalValueError("unsupported type in a canonical payload", path=path, type=type(value).__name__)


def canonical_json(payload: object) -> str:
    """Serialise a payload to the one and only canonical JSON form (section 4.1).

    The form is: keys sorted by code point, no whitespace, ``ensure_ascii=False`` so UTF-8 text
    stays readable, no floats at all, and no trailing newline. There is no second encoder in pmx:
    Exchange's float-tolerant ``stable_json`` does not exist here, because an observation carries
    no float and may therefore be hashed with this one.

    Args:
        payload: A structure of ``dict``, ``list``, ``tuple``, ``str``, ``int``, ``bool`` and
            ``None``. Call ``to_dict()`` yourself: a dataclass instance is refused, so nobody
            hashes a structure whose field order is an implementation detail.

    Returns:
        The canonical JSON string, without a newline.

    Raises:
        NonCanonicalValueError: If the payload holds a float, a set, ``bytes``, a non-str Enum, a
            non-string object key, or any other unsupported type.
    """
    return json.dumps(
        _encode(payload, "$"),
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_sha256(payload: object) -> str:
    """Return the SHA-256 hex digest of ``canonical_json(payload)``.

    This is the one spelling of the four content hashes of section 4.3 that are taken over a
    payload rather than over a file: ``genome_hash``, ``config_hash``, ``obs_sha256`` and the live
    ``forecast_hash``. Every caller passes an already-serialised mapping.

    Args:
        payload: Any canonically serialisable structure.

    Returns:
        A 64 character lowercase hex digest.

    Raises:
        NonCanonicalValueError: If the payload is not canonically serialisable.
    """
    return hashlib.sha256(canonical_json(payload).encode(JOURNAL_ENCODING)).hexdigest()


# --------------------------------------------------------------------------------------------------
# The event envelope (section 9.1)
# --------------------------------------------------------------------------------------------------
#: The four envelope fields declared on :class:`JournalEvent` itself. ``type`` is not among them:
#: it is derived from the ``TYPE`` class variable, so no emitter can misspell it.
_ENVELOPE_FIELD_NAMES: frozenset[str] = frozenset({"seq", "run_id", "bar_ms", "phase"})


@dataclass(frozen=True, slots=True, kw_only=True)
class JournalEvent:
    """Base class of every journal event: the five-field envelope minus the derived ``type``.

    Attributes:
        seq: Position in the journal, starting at 1 and incremented by exactly 1. Assigned by
            :class:`Journal` and by nothing else.
        run_id: The run this journal belongs to. A foreign ``run_id`` is refused at append time.
        bar_ms: The bar the event belongs to; ``0`` for ``run_started``, ``sealed_test_opened``
            and every evolution event, ``t1_ms`` for ``run_ended`` (section 9.1).
        phase: One of :data:`pmx.types.PHASE_ORDER`, and one of the phases the concrete class
            declares in ``PHASES``.

    Note:
        Events are frozen but not reliably hashable: some payloads hold mappings. Compare them by
        value, never put them in a ``set`` (which section 3 forbids for output anyway).

        A ``tuple`` field round-trips as a tuple, but a container *inside* a mapping field comes
        back as the ``list`` the JSON held, so an emitter hands mapping payloads the JSON shape
        they will be read as (which is what ``to_dict()`` of a config, a genome or a descriptor
        set already produces). The bytes are identical either way; only ``==`` between a written
        and a read event would notice.
    """

    seq: int
    run_id: str
    bar_ms: int
    phase: str

    #: Discriminator written as the ``type`` field. Set by every concrete subclass.
    TYPE: ClassVar[str]
    #: The phases this event may legally carry. One entry for all but two events of the
    #: catalogue, and :meth:`Journal.emit` fills it in when there is exactly one.
    PHASES: ClassVar[tuple[str, ...]]
    #: True when the event must carry ``bar_ms = 0`` (section 9.1).
    BAR_MS_ZERO: ClassVar[bool] = False
    #: ``"backtest"`` or ``"evolution"``. A journal never mixes the two (section 9.1).
    JOURNAL_KIND: ClassVar[str] = "backtest"

    def to_dict(self) -> dict[str, object]:
        """Return the flat mapping written to the journal, envelope first, then the payload.

        Returns:
            A dict holding ``seq``, ``type``, ``run_id``, ``bar_ms``, ``phase`` and every payload
            field of the concrete subclass, each canonically encoded (tuples become lists).

        Raises:
            NonCanonicalValueError: If a payload value is not canonically serialisable.
        """
        out: dict[str, object] = {
            "seq": self.seq,
            "type": self.TYPE,
            "run_id": self.run_id,
            "bar_ms": self.bar_ms,
            "phase": self.phase,
        }
        for name in payload_field_names(type(self)):
            out[name] = _encode(getattr(self, name), f"$.{name}")
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> JournalEvent:
        """Rebuild an event from its journal mapping.

        Called on :class:`JournalEvent` itself the concrete class is resolved from the ``type``
        field; called on a concrete subclass the ``type`` field is ignored.

        Args:
            data: The mapping produced by :meth:`to_dict`.

        Returns:
            The reconstructed event, with every ``tuple`` field a tuple again.

        Raises:
            JournalError: If a field is missing or the ``type`` is unknown.
        """
        if cls is JournalEvent:
            return event_from_dict(data)
        hints = _type_hints(cls)
        kwargs: dict[str, Any] = {}
        for field in fields(cls):
            if field.name not in data:
                raise JournalError(
                    "journal line is missing a field of its event type",
                    event_type=cls.TYPE,
                    field=field.name,
                )
            kwargs[field.name] = _coerce(hints.get(field.name), data[field.name])
        return cls(**kwargs)


#: Per-class caches, filled on first use. A plain dict rather than ``functools.cache`` because the
#: key is a class and a class is hashable in a way ``Hashable`` cannot express for ``type[T]``.
_PAYLOAD_FIELD_NAMES: dict[type[JournalEvent], tuple[str, ...]] = {}
_TYPE_HINTS: dict[type[JournalEvent], Mapping[str, object]] = {}


def payload_field_names(event_cls: type[JournalEvent]) -> tuple[str, ...]:
    """Return the payload field names of one event class, in declaration order.

    Cached: it runs once per event of every run, and rebuilding the ``fields()`` tuple each time
    made journal encoding a measurable share of a bar. The cache moves no byte, because the field
    order of a dataclass is fixed at class creation.

    Args:
        event_cls: A concrete :class:`JournalEvent` subclass.

    Returns:
        Every field name except the four envelope ones, in declaration order.
    """
    cached = _PAYLOAD_FIELD_NAMES.get(event_cls)
    if cached is None:
        cached = tuple(field.name for field in fields(event_cls) if field.name not in _ENVELOPE_FIELD_NAMES)
        _PAYLOAD_FIELD_NAMES[event_cls] = cached
    return cached


def _type_hints(event_cls: type[JournalEvent]) -> Mapping[str, object]:
    """Return the resolved annotations of an event class (this module uses future annotations)."""
    cached = _TYPE_HINTS.get(event_cls)
    if cached is None:
        resolved: dict[str, Any] = get_type_hints(event_cls)
        cached = resolved
        _TYPE_HINTS[event_cls] = cached
    return cached


def _coerce(annotation: object, value: object) -> object:
    """Convert a JSON value back into the type a dataclass field declares.

    Only the shapes the catalogue uses are handled: ``tuple[X, ...]``, ``Mapping``/``dict``,
    optionals of those, and the scalars, which pass through untouched.

    Args:
        annotation: The resolved annotation of the field, or ``None`` when unknown.
        value: The value read from the journal line.

    Returns:
        The value in the shape the dataclass expects.
    """
    if value is None:
        return None
    origin = get_origin(annotation)
    if origin is Union or origin is pytypes.UnionType:
        candidates = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(candidates) == 1:
            return _coerce(candidates[0], value)
        return value
    if origin is tuple:
        args = get_args(annotation)
        items = cast("Sequence[object]", value)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_coerce(args[0], item) for item in items)
        return tuple(items)
    if origin in (dict, Mapping) or annotation in (dict, Mapping):
        return dict(cast("Mapping[str, object]", value))
    return value


# --------------------------------------------------------------------------------------------------
# The backtest catalogue (section 9.2)
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True, kw_only=True)
class RunStarted(JournalEvent):
    """First event of a backtest journal: the whole provenance of the run, at ``bar_ms = 0``.

    ``config`` is ``RunConfig.to_dict()`` and ``roster`` one mapping per agent, in agent order.
    A replay refuses a journal whose ``engine_version`` differs from the running engine.
    """

    seed: int
    engine_version: str
    contract_version: str
    rng_algorithm_version: str
    dataset_name: str
    dataset_hash: str
    interval_min: int
    t0_ms: int
    t1_ms: int
    market_ids: tuple[str, ...]
    config: Mapping[str, object]
    config_hash: str
    folds: Mapping[str, int]
    memory_from_run_id: str | None
    memory_hash: str | None
    memory_from_run_t1_ms: int | None
    contamination_hash: str | None
    roster: tuple[Mapping[str, object], ...]

    TYPE: ClassVar[str] = "run_started"
    PHASES: ClassVar[tuple[str, ...]] = ("pre",)
    BAR_MS_ZERO: ClassVar[bool] = True


@dataclass(frozen=True, slots=True, kw_only=True)
class SealedTestOpened(JournalEvent):
    """O1's sealed-fold accessor read the fold for a named claim (section 12.7).

    Written before any market id is returned, so an aborted claim still leaves the peek on the
    record. It is the one event of this catalogue that neither the runner nor the optimizer emits.
    """

    claim_id: str
    dataset_hash: str
    genome_hash: str
    provider: str
    n_markets: int
    market_ids: tuple[str, ...]

    TYPE: ClassVar[str] = "sealed_test_opened"
    PHASES: ClassVar[tuple[str, ...]] = ("pre",)
    BAR_MS_ZERO: ClassVar[bool] = True


@dataclass(frozen=True, slots=True, kw_only=True)
class BarOpened(JournalEvent):
    """The market sets of one bar: open, tradable, settling, and newly listed this bar."""

    open_market_ids: tuple[str, ...]
    tradable_market_ids: tuple[str, ...]
    settling_market_ids: tuple[str, ...]
    listed_market_ids: tuple[str, ...]

    TYPE: ClassVar[str] = "bar_opened"
    PHASES: ClassVar[tuple[str, ...]] = ("open",)


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketListed(JournalEvent):
    """A market's leak-free metadata, once per run, at the first bar where it is open.

    An observed input, not a derived number: without it the projection could not rebuild the
    horizon buckets, the block keys or the per-category and per-fold rows from the journal alone
    (sections 9.2 and 9.5).
    """

    market_id: str
    provider: str
    category: str
    tags: tuple[str, ...]
    event_key: str | None
    created_at_ms: int
    close_at_ms: int
    interval_min: int
    fee_schedule_id: str
    hardness_tags: tuple[str, ...]
    fold: str
    #: Amendment C1b's eight instrument fields (17.3, ruling R164), required since gate G2 rebuilt the
    #: backtest fixture. On a binary they carry the mapping of 17.1 (``binary``, the provider, the
    #: ``provider_id``, ``100``, ``1_000_000``, ``continuous``, ``None``, ``None``); on a continuous
    #: instrument ``close_at_ms`` is ``delisted_at_ms`` or ``0`` when unset (a journal is not an observation).
    kind: str
    vendor: str
    symbol: str
    tick_size_micro: int
    point_value_micro: int
    session_calendar_id: str
    borrow_schedule_id: str | None
    carry_schedule_id: str | None

    TYPE: ClassVar[str] = "market_listed"
    PHASES: ClassVar[tuple[str, ...]] = ("open",)


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketPriced(JournalEvent):
    """The prices of one open market at one bar.

    ``close_bp`` is the close of the bar itself (the ``mark_price_bp`` of section 8.7) and
    ``last_close_bp`` the close of the last completed bar at the bar's open, which is the market's
    own forecast for that bar and ``first_price_bp`` when no bar is completed yet.
    """

    market_id: str
    close_bp: int
    last_close_bp: int
    vwap_bp: int
    volume_milli: int

    TYPE: ClassVar[str] = "market_priced"
    PHASES: ClassVar[tuple[str, ...]] = ("open",)


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderExpired(JournalEvent):
    """A resting order left the book without a fill, and its reservation was released."""

    order_id: str
    agent_id: str
    market_id: str
    remaining_size: int
    released_cents: int
    reason: str

    TYPE: ClassVar[str] = "order_expired"
    PHASES: ClassVar[tuple[str, ...]] = ("open", "settle", "close")


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationBuilt(JournalEvent):
    """The shape and the hash of one agent's observation, never its content.

    ``obs_sha256`` is ``canonical_sha256(observation.to_dict())``, which is legal in a journal
    because an observation carries no float (section 4.1).
    """

    agent_id: str
    n_markets: int
    n_news: int
    n_hive: int
    n_bars_max: int
    research_remaining: int
    bytes: int
    obs_sha256: str

    TYPE: ClassVar[str] = "observation_built"
    PHASES: ClassVar[tuple[str, ...]] = ("observe",)


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplyReceived(JournalEvent):
    """An LLM seat answered (or its fallback did). ``error`` is a ``RejectReason``, never text."""

    agent_id: str
    source: str
    error: str | None
    schema_valid: bool
    n_lessons: int

    TYPE: ClassVar[str] = "reply_received"
    PHASES: ClassVar[tuple[str, ...]] = ("decide",)


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionReceived(JournalEvent):
    """One agent's validated decision for one bar: the intents that survived validation."""

    agent_id: str
    source: str
    intents: tuple[Mapping[str, object], ...]
    research: Mapping[str, object] | None
    notes: str
    n_lessons: int
    n_rejected: int

    TYPE: ClassVar[str] = "action_received"
    PHASES: ClassVar[tuple[str, ...]] = ("decide",)


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionRejected(JournalEvent):
    """One item of a reply was refused, with the scope it was refused in and why."""

    agent_id: str
    market_id: str | None
    scope: str
    item_index: int
    reason: str
    detail: str

    TYPE: ClassVar[str] = "action_rejected"
    PHASES: ClassVar[tuple[str, ...]] = ("decide",)


@dataclass(frozen=True, slots=True, kw_only=True)
class ForecastRecorded(JournalEvent):
    """One agent's probability on one open market for this bar.

    ``carried`` marks a forecast the engine carried forward (a silent agent, or a ruined one:
    section 8.2 keeps scoring it so dying cannot drop the markets it was losing on).
    """

    agent_id: str
    market_id: str
    prob_ppm: int
    carried: bool
    #: Amendment C1b's continuous payload (17.5, ruling R157): the reference price in ticks and one
    #: ``{horizon_bars, up_probability_ppm, quantiles_ticks}`` mapping per horizon of the run. ``None`` on
    #: a binary (ruling R164 as applied by gate G2: one event shape per name, null where the kind has no
    #: value, exactly as ``event_key`` and ``market_id`` are nullable elsewhere in the catalogue).
    price_ref_ticks: int | None
    horizons: tuple[Mapping[str, object], ...] | None

    TYPE: ClassVar[str] = "forecast_recorded"
    PHASES: ClassVar[tuple[str, ...]] = ("decide",)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchSpent(JournalEvent):
    """A research request, its price in units, what is left, and whether it was granted."""

    agent_id: str
    kind: str
    market_id: str | None
    units: int
    remaining: int
    granted: bool

    TYPE: ClassVar[str] = "research_spent"
    PHASES: ClassVar[tuple[str, ...]] = ("decide",)


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryWritten(JournalEvent):
    """One memory record was written, at ``decide`` for an LLM lesson or at ``learn``."""

    agent_id: str
    kind: str
    key: str
    payload: Mapping[str, object]
    bytes_after: int

    TYPE: ClassVar[str] = "memory_written"
    PHASES: ClassVar[tuple[str, ...]] = ("decide", "learn")


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderPlaced(JournalEvent):
    """An order entered the book, with the cash it reserved and the intent it came from."""

    order_id: str
    agent_id: str
    market_id: str
    kind: str
    side: str
    price_bp: int | None
    size: int
    ttl_bars: int | None
    expires_at_ms: int | None
    reserved_cents: int
    origin: str
    #: The bar the intent was decided at: the instrument's previous bar (section 16.2, rulings R111, R129
    #: and R192), or the bar itself for an event fill, whose phase is ``settle`` (17.3, ruling R152).
    decided_at_ms: int

    TYPE: ClassVar[str] = "order_placed"
    PHASES: ClassVar[tuple[str, ...]] = ("execute", "settle")


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderRejected(JournalEvent):
    """An intent was refused at the execution boundary (section 8.6 step 0 and after)."""

    agent_id: str
    market_id: str
    item_index: int
    reason: str
    detail: str
    #: The bar the rejected intent was decided at (16.2, ruling R129): without it ``item_index``, which
    #: indexes the previous bar's ``action_received``, could not be traced to its intent.
    decided_at_ms: int

    TYPE: ClassVar[str] = "order_rejected"
    PHASES: ClassVar[tuple[str, ...]] = ("execute",)


@dataclass(frozen=True, slots=True, kw_only=True)
class Filled(JournalEvent):
    """One fill, whole or partial, with the price it was built from and the cash it moved.

    A cent moves in exactly one of ``filled.cash_delta_cents``, ``fee_charged.fee_cents`` and
    ``settlement_applied.cash_delta_cents`` (section 9.3), which is what makes the accounting
    invariant of section 8.9 checkable from the journal alone.
    """

    order_id: str
    agent_id: str
    market_id: str
    side: str
    kind: str
    requested_size: int
    filled_size: int
    unfilled_size: int
    unfilled_reason: str
    base_price_bp: int
    slippage_bp: int
    fill_price_bp: int
    price_source: str
    close_size: int
    open_size: int
    cash_delta_cents: int
    released_cents: int
    position_before: int
    position_after: int
    avg_cost_bp_after: int

    TYPE: ClassVar[str] = "filled"
    #: ``settle`` for an event fill of a roll or the forced flat (17.3, rulings R152 and R164).
    PHASES: ClassVar[tuple[str, ...]] = ("execute", "settle")


@dataclass(frozen=True, slots=True, kw_only=True)
class FeeCharged(JournalEvent):
    """The fee of one fill, from the provider schedule named in ``schedule_id``."""

    order_id: str
    agent_id: str
    market_id: str
    fee_cents: int
    schedule_id: str
    role: str

    TYPE: ClassVar[str] = "fee_charged"
    #: ``settle`` for the taker fee of an event fill (17.3, rulings R152 and R164).
    PHASES: ClassVar[tuple[str, ...]] = ("execute", "settle")


@dataclass(frozen=True, slots=True, kw_only=True)
class Settled(JournalEvent):
    """A market resolved: the outcome, the payout, and the market's own life-long score."""

    market_id: str
    outcome: int
    payout_bp: int
    resolved_at_ms: int
    n_bars: int
    market_brier_tw_micro: int
    life_mean_price_bp: int

    TYPE: ClassVar[str] = "settled"
    PHASES: ClassVar[tuple[str, ...]] = ("settle",)


@dataclass(frozen=True, slots=True, kw_only=True)
class SettlementApplied(JournalEvent):
    """What the settlement of one market did to one agent: cash, realised PnL and its Brier."""

    agent_id: str
    market_id: str
    position: int
    cash_delta_cents: int
    cash_after_cents: int
    realised_pnl_cents: int
    agent_brier_tw_micro: int
    n_forecast_bars: int

    TYPE: ClassVar[str] = "settlement_applied"
    PHASES: ClassVar[tuple[str, ...]] = ("settle",)


@dataclass(frozen=True, slots=True, kw_only=True)
class CashEventApplied(JournalEvent):
    """One ``CashEvent`` of section 17.3 applied to one agent in the settle phase (ruling R151).

    ``cash_delta_cents`` is the one money-moving field for ``funding``, ``dividend``, ``borrow_fee`` and
    ``carry`` (signed: a debit may take cash below zero, ruling R179) and is ``0`` for ``split``, ``roll``
    and ``forced_flat``, whose money moves in the ``filled`` and ``fee_charged`` events named in
    ``order_ids``. ``position_before`` and ``position_after`` are the position before the first and after
    the last of those event fills for ``roll`` and ``forced_flat``, equal for the four charges, and related
    by ``split_position_milli`` for a split (ruling R178). Emitted by ``pmx.engine.execution`` only (9.3).
    """

    agent_id: str
    market_id: str
    cash_event_id: str
    kind: str
    origin: str
    position_before: int
    position_after: int
    avg_cost_ticks_before: int
    avg_cost_ticks_after: int
    cash_delta_cents: int
    order_ids: tuple[str, ...]
    detail: Mapping[str, object]

    TYPE: ClassVar[str] = "cash_event_applied"
    PHASES: ClassVar[tuple[str, ...]] = ("settle",)


@dataclass(frozen=True, slots=True, kw_only=True)
class InstrumentClosed(JournalEvent):
    """A continuous instrument's last bar in the run (17.3, ruling R150): every position has been
    flattened by ``Execution.force_flat`` and the runner records what the instrument was.

    ``n_bars`` counts the instrument's bars inside the run and ``n_forecasts_unresolved`` the horizon
    forecasts whose horizon lies beyond it, which are never scored (ruling R160).
    """

    market_id: str
    kind: str
    reason: str
    last_price_ticks: int
    n_bars: int
    n_forecasts_unresolved: int

    TYPE: ClassVar[str] = "instrument_closed"
    PHASES: ClassVar[tuple[str, ...]] = ("settle",)


@dataclass(frozen=True, slots=True, kw_only=True)
class ForecastResolved(JournalEvent):
    """One horizon of one continuous forecast, scored at the bar its realisation became public (17.5,
    ruling R160).

    The baseline directional Brier is the constant ``RANDOM_WALK_BRIER_MICRO`` and is not a field; the
    baseline pinball depends on the realisation and is. ``pinball_micro`` is ``None`` for an agent that
    stated no quantiles, which is scored on direction only and says so.
    """

    agent_id: str
    market_id: str
    forecast_bar_ms: int
    horizon_bars: int
    up_probability_ppm: int
    quantiles_ticks: tuple[int, ...] | None
    price_ref_ticks: int
    price_realised_ticks: int
    realised_sign: int
    directional_brier_micro: int
    pinball_micro: int | None
    baseline_pinball_micro: int
    carried: bool

    TYPE: ClassVar[str] = "forecast_resolved"
    PHASES: ClassVar[tuple[str, ...]] = ("settle",)


@dataclass(frozen=True, slots=True, kw_only=True)
class HiveWritten(JournalEvent):
    """One hive entry, with the bar it becomes visible at.

    A ``forecast`` or ``resolution`` entry is stamped ``bar_of(resolved_at_ms) + interval_ms``, so
    the as-of filter releases it at the first bar strictly after the settling bar and no agent
    ever reads another agent's forecast on a market that is still open (sections 5.4 and 10.4).
    """

    entry_id: str
    kind: str
    author_id: str
    market_id: str | None
    visible_from_ms: int
    payload: Mapping[str, object]

    TYPE: ClassVar[str] = "hive_written"
    PHASES: ClassVar[tuple[str, ...]] = ("hive",)


@dataclass(frozen=True, slots=True, kw_only=True)
class EquityMarked(JournalEvent):
    """One agent's book at the close of one bar, marked at ``mark_price_bp`` (section 8.7)."""

    agent_id: str
    cash_cents: int
    reserved_cents: int
    positions_value_cents: int
    equity_cents: int
    fees_paid_cents: int
    peak_equity_cents: int
    drawdown_bp: int
    n_open_positions: int
    n_open_orders: int

    TYPE: ClassVar[str] = "equity_marked"
    PHASES: ClassVar[tuple[str, ...]] = ("close",)


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentRuined(JournalEvent):
    """An agent fell through the ruin floor; its resting orders were cancelled."""

    agent_id: str
    equity_cents: int
    cancelled_order_ids: tuple[str, ...]

    TYPE: ClassVar[str] = "agent_ruined"
    PHASES: ClassVar[tuple[str, ...]] = ("close",)


@dataclass(frozen=True, slots=True, kw_only=True)
class BarClosed(JournalEvent):
    """The last event of a bar, counting the events of that bar including itself."""

    n_events: int

    TYPE: ClassVar[str] = "bar_closed"
    PHASES: ClassVar[tuple[str, ...]] = ("close",)


@dataclass(frozen=True, slots=True, kw_only=True)
class RunEnded(JournalEvent):
    """Last event of a backtest journal, at ``bar_ms = t1_ms`` (section 9.1)."""

    reason: str
    final_bar_ms: int
    n_bars: int
    event_count: int
    ruined_agent_ids: tuple[str, ...]

    TYPE: ClassVar[str] = "run_ended"
    PHASES: ClassVar[tuple[str, ...]] = ("post",)


# --------------------------------------------------------------------------------------------------
# The evolution catalogue (section 9.4). ``bar_ms`` is 0 throughout, and a journal never mixes
# these with the bar events of a backtest.
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True, kw_only=True)
class EvolutionStarted(JournalEvent):
    """First event of an evolution journal: the seed, the config and the initial population."""

    seed: int
    engine_version: str
    contract_version: str
    dataset_hash: str
    config: Mapping[str, object]
    config_hash: str
    population_size: int
    max_generations: int
    folds: Mapping[str, int]
    initial_population: tuple[Mapping[str, object], ...]

    TYPE: ClassVar[str] = "evolution_started"
    PHASES: ClassVar[tuple[str, ...]] = ("pre",)
    BAR_MS_ZERO: ClassVar[bool] = True
    JOURNAL_KIND: ClassVar[str] = "evolution"


@dataclass(frozen=True, slots=True, kw_only=True)
class GenerationStarted(JournalEvent):
    """One generation opened, with the derived run seed and the two backtest run ids it will use."""

    generation: int
    run_seed: int
    train_run_id: str
    validation_run_id: str
    population: tuple[str, ...]

    TYPE: ClassVar[str] = "generation_started"
    PHASES: ClassVar[tuple[str, ...]] = ("generation",)
    BAR_MS_ZERO: ClassVar[bool] = True
    JOURNAL_KIND: ClassVar[str] = "evolution"


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateScored(JournalEvent):
    """One candidate's result on one fold, lower bounds included (section 12.4)."""

    generation: int
    agent_id: str
    genome_hash: str
    fold: str
    n_markets: int
    skill_point_micro: int
    skill_lb_micro: int
    pnl_point_cents: int
    pnl_lb_cents: int
    brier_tw_micro: int
    ruined: bool
    research_units_spent: int
    descriptors: Mapping[str, int]

    TYPE: ClassVar[str] = "candidate_scored"
    PHASES: ClassVar[tuple[str, ...]] = ("generation",)
    BAR_MS_ZERO: ClassVar[bool] = True
    JOURNAL_KIND: ClassVar[str] = "evolution"


@dataclass(frozen=True, slots=True, kw_only=True)
class GenerationClosed(JournalEvent):
    """The ranking, the cull, the children, the archive and the patience left after a generation.

    ``candidates_evaluated_cum`` counts distinct genome hashes ever scored on the validation fold
    in this evolution run; it is ``0`` for a generation that validated nothing (section 9.4).
    """

    generation: int
    ranked: tuple[Mapping[str, object], ...]
    culled: tuple[str, ...]
    elites: tuple[str, ...]
    children: tuple[Mapping[str, object], ...]
    archive: tuple[Mapping[str, object], ...]
    archive_filled: int
    archive_cells: int
    hall_of_fame: tuple[Mapping[str, object], ...]
    candidates_evaluated_cum: int
    best_validation_lb_micro: int
    patience_left: int
    research_budget_next: Mapping[str, int]

    TYPE: ClassVar[str] = "generation_closed"
    PHASES: ClassVar[tuple[str, ...]] = ("generation",)
    BAR_MS_ZERO: ClassVar[bool] = True
    JOURNAL_KIND: ClassVar[str] = "evolution"


@dataclass(frozen=True, slots=True, kw_only=True)
class EvolutionEnded(JournalEvent):
    """Last event of an evolution journal: why it stopped and which genome won."""

    reason: str
    generations_run: int
    candidates_evaluated_cum: int
    champion: Mapping[str, object]

    TYPE: ClassVar[str] = "evolution_ended"
    PHASES: ClassVar[tuple[str, ...]] = ("post",)
    BAR_MS_ZERO: ClassVar[bool] = True
    JOURNAL_KIND: ClassVar[str] = "evolution"


#: Every concrete event class, in the order of the catalogue of sections 9.2 and 9.4.
_EVENT_CLASS_TUPLE: tuple[type[JournalEvent], ...] = (
    RunStarted,
    SealedTestOpened,
    BarOpened,
    MarketListed,
    MarketPriced,
    OrderExpired,
    ObservationBuilt,
    ReplyReceived,
    ActionReceived,
    ActionRejected,
    ForecastRecorded,
    ResearchSpent,
    MemoryWritten,
    OrderPlaced,
    OrderRejected,
    Filled,
    FeeCharged,
    Settled,
    SettlementApplied,
    CashEventApplied,
    InstrumentClosed,
    ForecastResolved,
    HiveWritten,
    EquityMarked,
    AgentRuined,
    BarClosed,
    RunEnded,
    EvolutionStarted,
    GenerationStarted,
    CandidateScored,
    GenerationClosed,
    EvolutionEnded,
)

#: ``type`` string to concrete class. The one resolver used by :func:`event_from_dict`.
EVENT_CLASSES: Mapping[str, type[JournalEvent]] = {cls.TYPE: cls for cls in _EVENT_CLASS_TUPLE}
#: The event names of the catalogue, in catalogue order.
EVENT_TYPES: tuple[str, ...] = tuple(cls.TYPE for cls in _EVENT_CLASS_TUPLE)

#: The last event of a journal, per kind (section 9.1).
_TERMINAL_TYPES: frozenset[str] = frozenset({RunEnded.TYPE, EvolutionEnded.TYPE})
#: The only legal ``seq == 1`` events (section 9.1, ruling R46).
_OPENING_TYPES: frozenset[str] = frozenset({RunStarted.TYPE, EvolutionStarted.TYPE})


# --------------------------------------------------------------------------------------------------
# Lines, hashes and schema validation
# --------------------------------------------------------------------------------------------------
def event_from_dict(data: Mapping[str, object]) -> JournalEvent:
    """Rebuild the right concrete event from a journal mapping.

    Args:
        data: Mapping holding at least a ``type`` key.

    Returns:
        The reconstructed event.

    Raises:
        JournalError: If ``type`` is missing, is not a string, or is not in the catalogue.
    """
    raw_type = data.get("type")
    if not isinstance(raw_type, str):
        raise JournalError("journal line has no string 'type' field", type=repr(raw_type))
    event_cls = EVENT_CLASSES.get(raw_type)
    if event_cls is None:
        raise JournalError("unknown event type", event_type=raw_type)
    return event_cls.from_dict(data)


def event_to_line(event: JournalEvent) -> str:
    r"""Serialise one event to its journal line, newline included.

    Args:
        event: The event.

    Returns:
        ``canonical_json(event.to_dict()) + "\n"``.

    Raises:
        NonCanonicalValueError: If a payload value is not canonically serialisable.
    """
    return canonical_json(event.to_dict()) + JOURNAL_NEWLINE


def event_from_line(line: str) -> JournalEvent:
    """Parse one journal line back into an event.

    Args:
        line: A single JSONL line, with or without its trailing newline.

    Returns:
        The reconstructed event.

    Raises:
        JournalError: If the line is not a JSON object, or not a known event.
        NonCanonicalValueError: If the line holds a carriage return.
    """
    _reject_carriage_return(line, 0)
    parsed: object = json.loads(line)
    if not isinstance(parsed, dict):
        raise JournalError("journal line is not a JSON object")
    return event_from_dict(cast("Mapping[str, object]", parsed))


def _reject_carriage_return(line: str, index: int) -> None:
    r"""Raise when a journal line holds a carriage return (section 4.2).

    Args:
        line: The raw line, read with ``newline=JOURNAL_NEWLINE``.
        index: 0 based position of the line in the file, for the error context.

    Raises:
        NonCanonicalValueError: If the line contains ``"\r"``.
    """
    if "\r" in line:
        raise NonCanonicalValueError(
            "journal lines must use LF endings; open the file with newline=JOURNAL_NEWLINE",
            path=f"$[{index}]",
            value="carriage return",
        )


def journal_hash(events: Iterable[JournalEvent]) -> str:
    """Compute the ``journal_hash`` of section 4.3 over events.

    The digest is SHA-256 over the concatenation of every canonical event line, which is byte for
    byte the content of ``journal.jsonl``.

    Args:
        events: Events in ``seq`` order.

    Returns:
        A 64 character lowercase hex digest.
    """
    digest = hashlib.sha256()
    for event in events:
        digest.update(event_to_line(event).encode(JOURNAL_ENCODING))
    return digest.hexdigest()


def journal_hash_from_lines(lines: Iterable[str]) -> str:
    r"""Compute the journal digest from raw file lines.

    A carriage return anywhere in a line is rejected rather than normalised away: reading a CRLF
    file in universal-newline mode hands back clean ``"\n"`` lines, so a journal accidentally
    written in the platform default text mode on Windows would hash *correctly* here while its
    bytes on disk hashed differently, and AC-3 would only fail once two machines compared files.

    Args:
        lines: Journal lines, each with or without its trailing newline, in file order.

    Returns:
        A 64 character lowercase hex digest, identical to :func:`journal_hash` over the same
        events.

    Raises:
        NonCanonicalValueError: If a line contains a carriage return.
    """
    digest = hashlib.sha256()
    for index, line in enumerate(lines):
        _reject_carriage_return(line, index)
        text = line if line.endswith(JOURNAL_NEWLINE) else line + JOURNAL_NEWLINE
        digest.update(text.encode(JOURNAL_ENCODING))
    return digest.hexdigest()


def journal_hash_of_file(path: Path) -> str:
    r"""Compute the journal digest over the exact bytes of a file (section 4.3).

    This is what ``journal.sha256`` records and what ``pmx replay`` verifies. The bytes are read
    in binary and a ``\r`` anywhere in them is refused, so a CRLF journal fails here rather than
    on another machine.

    Args:
        path: The ``journal.jsonl`` file.

    Returns:
        A 64 character lowercase hex digest.

    Raises:
        NonCanonicalValueError: If the file holds a carriage return.
    """
    raw = path.read_bytes()
    if b"\r" in raw:
        raise NonCanonicalValueError(
            "journal file holds a carriage return; it was written in the platform text mode",
            path=path.as_posix(),
            value="carriage return",
        )
    return hashlib.sha256(raw).hexdigest()


def validate_event_dict(payload: Mapping[str, object]) -> None:
    """Validate one event mapping against ``schemas/journal.v2.json``.

    The schema is the third line of defence behind :func:`canonical_json` and D1's strict integer
    models (section 4.1): it pins the envelope, the phase of every event type and the field set,
    which is what makes a journal written by a future package legible to this one. The validator
    itself is D1's (section 7.13: one resolver, no package builds a schema path of its own); this
    wrapper only says which event failed.

    Args:
        payload: The mapping produced by :meth:`JournalEvent.to_dict`.

    Raises:
        SchemaError: If the mapping does not validate, naming the failing path and the event.
    """
    where = f"journal event seq={payload.get('seq')} type={payload.get('type')}"
    raw_type = payload.get("type")
    if isinstance(raw_type, str) and raw_type in EVENT_CLASSES:
        # Dispatch on ``type`` (gate G2 ruling, answering E5's report): the schema's ``oneOf`` with
        # ``unevaluatedProperties: false`` made the validator try every one of thirty-two branches per
        # event, about 27 ms each, so a whole-pack journal took seven minutes to validate and the real
        # dataset's would have taken hours. The per-type sub-schema is the same ``$defs`` entry the
        # ``oneOf`` would have selected; an unknown type still goes through the whole schema so the
        # failure it reports is the ``oneOf`` one.
        errors = sorted(
            _validator_for_type(raw_type).iter_errors(dict(payload)),
            key=lambda e: (list(e.absolute_path), e.message),
        )
        if not errors:
            return
        first = errors[0]
        raise SchemaError(
            "payload fails its JSON schema",
            schema=JOURNAL_SCHEMA,
            where=where,
            at="/".join(str(part) for part in first.absolute_path),
            detail=first.message,
            n_errors=len(errors),
        )
    validate_against_schema(JOURNAL_SCHEMA, dict(payload), where=where)


_TYPE_VALIDATORS: dict[str, Draft202012Validator] = {}


def _validator_for_type(event_type: str) -> Draft202012Validator:
    """The compiled validator of one event type's ``$defs`` entry, built once per process."""
    cached = _TYPE_VALIDATORS.get(event_type)
    if cached is None:
        schema = load_schema(JOURNAL_SCHEMA)
        defs = schema["$defs"]
        if not isinstance(defs, dict):  # pragma: no cover - the schema file is C1b's and carries $defs
            raise SchemaError("journal schema carries no $defs", schema=JOURNAL_SCHEMA)
        sub: dict[str, object] = {
            "$schema": schema.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
            "$ref": f"#/$defs/{event_type}",
            "$defs": defs,
        }
        Draft202012Validator.check_schema(sub)
        cached = Draft202012Validator(sub)
        _TYPE_VALIDATORS[event_type] = cached
    return cached


# --------------------------------------------------------------------------------------------------
# The writer
# --------------------------------------------------------------------------------------------------
def _open_for_write(path: Path, mode: Literal["w", "a"]) -> TextIO:
    """Open a journal file with the one and only legal set of arguments (section 4.2).

    Args:
        path: Target file. Missing parent directories are created.
        mode: ``"w"`` for a fresh file, ``"a"`` for an append.

    Returns:
        The open text handle: UTF-8 without a BOM, LF only.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    return open(path, mode, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE)


def _forbidden_reason(name: str) -> str | None:
    """Return why ``name`` may not be a journal payload field, or ``None`` when it may.

    Args:
        name: A payload field name an emitter passed.

    Returns:
        A message naming what the field is (a wall clock, a duration, a provider metric, free
        provider text) and where it belongs instead, or ``None``.
    """
    forbidden = (
        name in FORBIDDEN_PAYLOAD_FIELDS
        or name.startswith(_FORBIDDEN_PREFIXES)
        or name.endswith(_FORBIDDEN_SUFFIXES)
    )
    if forbidden:
        return (
            "a wall clock, a duration, a provider cost, a token or retry count and free provider "
            "text vary between two runs of the same seed; they belong in llm_trace.jsonl, which is "
            "outside every hash (CONTRACTS_V2 section 4.4)"
        )
    return None


class Journal:
    r"""Append-only event log: the only writer of ``journal.jsonl``.

    The file is opened exactly as ``open(path, "w", encoding=JOURNAL_ENCODING,
    newline=JOURNAL_NEWLINE)``. Never the text-mode default: on Windows it turns ``"\n"`` into
    ``"\r\n"`` and the bytes on disk stop matching :meth:`hash`.

    A journal with ``path=None`` is a pure in-memory log: it validates, numbers and encodes events
    exactly the same way, and :meth:`hash` returns the digest a written file would have. That is
    the mode most tests use.

    The state is exposed through read-only properties on purpose: a ``seq`` assigned twice, or a
    ``run_id`` changed halfway through, is an AC-3 failure that no later check can repair.
    """

    __slots__ = (
        "_buffer_size",
        "_closed",
        "_events",
        "_handle",
        "_path",
        "_pending",
        "_run_id",
        "_tail_from",
        "_validate",
    )

    def __init__(
        self,
        run_id: str,
        path: Path | None = None,
        *,
        buffer_size: int = 256,
        validate: bool = False,
    ) -> None:
        """Open a fresh journal for one run.

        Args:
            run_id: The run this journal belongs to. Every appended event must carry exactly this
                id (section 2 gives the ``r-`` and ``e-`` formats).
            path: Destination file, or ``None`` for an in-memory journal. Parent directories are
                created. An existing file is truncated: a journal is written once, from ``seq`` 1.
            buffer_size: Number of pending lines held before they are handed to the operating
                system. At least 1. It changes nothing about the bytes, only how often they are
                written.
            validate: When True every event is also validated against ``journal.v2.json`` at
                append time. Off by default because a validator call per event is the single most
                expensive thing in a bar; on in the tests and wherever a new emitter lands.

        Raises:
            JournalError: If ``buffer_size`` is below 1.
        """
        if buffer_size < 1:
            raise JournalError("buffer_size must be at least 1", buffer_size=buffer_size)
        self._run_id = run_id
        self._path = path
        self._events: list[JournalEvent] = []
        self._tail_from = 0
        self._pending: list[str] = []
        self._buffer_size = buffer_size
        self._validate = validate
        self._closed = False
        self._handle: TextIO | None = _open_for_write(path, "w") if path is not None else None

    # ----------------------------------------------------------------------
    # Read-only state
    # ----------------------------------------------------------------------
    @property
    def run_id(self) -> str:
        """The run id every event of this journal carries."""
        return self._run_id

    @property
    def path(self) -> Path | None:
        """Destination file, or ``None`` for an in-memory journal."""
        return self._path

    @property
    def next_seq(self) -> int:
        """The ``seq`` the next appended event must carry. Starts at 1."""
        return len(self._events) + 1

    @property
    def events(self) -> tuple[JournalEvent, ...]:
        """Every event appended so far, in ``seq`` order."""
        return tuple(self._events)

    def take_tail(self) -> tuple[JournalEvent, ...]:
        """The events appended since the previous call, then forgotten (section 9.1, ruling R220).

        The runner reads the fills and fees execution just journaled to build ``settlement_applied``
        (section 8.7) rather than keeping a second ledger; reading them through :attr:`events` copied the
        whole journal on every bar and was quadratic. This is the same events in linear time, and it
        changes no byte: the journal is what it was, only read from a cursor.
        """
        tail = tuple(self._events[self._tail_from :])
        self._tail_from = len(self._events)
        return tail

    @property
    def closed(self) -> bool:
        """True once :meth:`close` ran; further appends are refused."""
        return self._closed

    # ----------------------------------------------------------------------
    # Writing
    # ----------------------------------------------------------------------
    def emit(self, event_cls: type[E], *, bar_ms: int, phase: str | None = None, **payload: object) -> E:
        """Build the event with the next ``seq`` and this ``run_id``, append it, return it.

        This is the call every emitter of section 9.3 uses. The envelope is never passed by the
        caller, which is what stops two emitters from choosing the same ``seq``, and ``phase``
        defaults to the one phase the event type declares (only ``order_expired`` and
        ``memory_written`` have more than one, and they must say which).

        Args:
            event_cls: A concrete event class of the catalogue.
            bar_ms: The bar the event belongs to; ``0`` for the events section 9.1 pins there.
            phase: The phase, when the event type allows more than one.
            **payload: The event's own fields, by keyword.

        Returns:
            The freshly built and appended event, typed as the class passed in.

        Raises:
            JournalError: On a forbidden field name (a wall clock, a duration, a provider metric),
                an unknown or missing field, an illegal or ambiguous phase, a ``bar_ms`` that must
                be ``0`` and is not, or a closed or already-ended journal.
            NonCanonicalValueError: If a payload value is not canonically serialisable (a float, a
                set, an unsupported type).
            SchemaError: If the journal validates and the event does not.
        """
        expected = frozenset(payload_field_names(event_cls))
        provided = frozenset(payload)
        unknown = sorted(provided - expected)
        for name in unknown:
            reason = _forbidden_reason(name)
            if reason is not None:
                raise JournalError(reason, event_type=event_cls.TYPE, field=name)
        if unknown:
            raise JournalError(
                "payload field is not in this event's catalogue entry",
                event_type=event_cls.TYPE,
                fields=",".join(unknown),
            )
        missing = sorted(expected - provided)
        if missing:
            raise JournalError(
                "payload is missing a field of this event's catalogue entry",
                event_type=event_cls.TYPE,
                fields=",".join(missing),
            )
        resolved_phase = self._resolve_phase(event_cls, phase)
        if event_cls.BAR_MS_ZERO and bar_ms != 0:
            raise JournalError(
                "this event type carries bar_ms 0 (CONTRACTS_V2 section 9.1)",
                event_type=event_cls.TYPE,
                bar_ms=bar_ms,
            )
        kwargs: dict[str, Any] = dict(payload)
        kwargs.update(seq=self.next_seq, run_id=self._run_id, bar_ms=bar_ms, phase=resolved_phase)
        event = event_cls(**kwargs)
        self.append(event)
        return event

    @staticmethod
    def _resolve_phase(event_cls: type[JournalEvent], phase: str | None) -> str:
        """Return the phase to stamp on an event, refusing an ambiguous or illegal one."""
        if phase is None:
            if len(event_cls.PHASES) != 1:
                raise JournalError(
                    "this event type has several legal phases; name the one you mean",
                    event_type=event_cls.TYPE,
                    phases=",".join(event_cls.PHASES),
                )
            return event_cls.PHASES[0]
        if phase not in event_cls.PHASES:
            raise JournalError(
                "phase is not legal for this event type",
                event_type=event_cls.TYPE,
                phase=phase,
                phases=",".join(event_cls.PHASES),
            )
        return phase

    def append(self, event: JournalEvent) -> JournalEvent:
        """Append a pre-built event, checking the envelope and the ordering of section 9.1.

        The line is encoded here, before the event is kept, so a float or a bad envelope fails at
        the emitting call site and fails for an in-memory journal too.

        Args:
            event: An event whose ``seq`` is exactly :attr:`next_seq` and whose ``run_id`` is
                exactly :attr:`run_id`.

        Returns:
            The event that was appended, unchanged.

        Raises:
            JournalError: On a closed journal, an append after the terminal event, a ``seq`` gap, a
                foreign ``run_id``, an illegal opening event, a decreasing ``bar_ms``, a phase
                going backwards inside a bar, or a backtest event in an evolution journal.
            NonCanonicalValueError: If the event cannot be canonically encoded.
            SchemaError: If the journal validates and the event does not.
        """
        if self._closed:
            raise JournalError("journal is closed", run_id=self._run_id, seq=event.seq)
        self._check_envelope(event)
        payload = event.to_dict()
        if self._validate:
            validate_event_dict(payload)
        line = canonical_json(payload) + JOURNAL_NEWLINE
        self._events.append(event)
        if self._handle is not None:
            self._pending.append(line)
            if len(self._pending) >= self._buffer_size:
                self.flush()
        return event

    def _check_envelope(self, event: JournalEvent) -> None:
        """Apply the append-time half of the guarantees :func:`verify_journal` re-checks."""
        if event.seq != self.next_seq:
            raise JournalError(
                "journal seq must increase by exactly 1",
                run_id=self._run_id,
                expected_seq=self.next_seq,
                actual_seq=event.seq,
                event_type=event.TYPE,
            )
        if event.run_id != self._run_id:
            raise JournalError(
                "event belongs to another run",
                expected_run_id=self._run_id,
                actual_run_id=event.run_id,
                seq=event.seq,
            )
        if event.phase not in event.PHASES:
            raise JournalError(
                "phase is not legal for this event type",
                event_type=event.TYPE,
                phase=event.phase,
                phases=",".join(event.PHASES),
            )
        if event.BAR_MS_ZERO and event.bar_ms != 0:
            raise JournalError(
                "this event type carries bar_ms 0 (CONTRACTS_V2 section 9.1)",
                event_type=event.TYPE,
                bar_ms=event.bar_ms,
            )
        if not self._events:
            if event.TYPE not in _OPENING_TYPES:
                raise JournalError(
                    "seq 1 is run_started or evolution_started (CONTRACTS_V2 section 9.1)",
                    run_id=self._run_id,
                    event_type=event.TYPE,
                )
            return
        previous = self._events[-1]
        if previous.TYPE in _TERMINAL_TYPES:
            raise JournalError(
                "the terminal event is the last event of a journal",
                run_id=self._run_id,
                terminal_type=previous.TYPE,
                event_type=event.TYPE,
            )
        if event.JOURNAL_KIND != self._events[0].JOURNAL_KIND:
            raise JournalError(
                "a journal never mixes a backtest with an evolution (CONTRACTS_V2 section 9.1)",
                run_id=self._run_id,
                journal_kind=self._events[0].JOURNAL_KIND,
                event_type=event.TYPE,
            )
        if event.bar_ms < previous.bar_ms:
            raise JournalError(
                "journal bar_ms must never decrease",
                run_id=self._run_id,
                seq=event.seq,
                previous_bar_ms=previous.bar_ms,
                actual_bar_ms=event.bar_ms,
            )
        if event.bar_ms == previous.bar_ms and PHASE_ORDER.index(event.phase) < PHASE_ORDER.index(previous.phase):
            raise JournalError(
                "phase must never go backwards inside one bar",
                run_id=self._run_id,
                seq=event.seq,
                bar_ms=event.bar_ms,
                previous_phase=previous.phase,
                actual_phase=event.phase,
            )

    def flush(self) -> None:
        """Write every pending line and flush the handle. A no-op in memory."""
        handle = self._handle
        if handle is None:
            self._pending.clear()
            return
        if self._pending:
            handle.write("".join(self._pending))
            self._pending.clear()
        handle.flush()

    def close(self) -> None:
        """Flush and close the file. Idempotent; further appends are refused."""
        if self._closed:
            return
        self.flush()
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        self._closed = True

    # ----------------------------------------------------------------------
    # Hashing
    # ----------------------------------------------------------------------
    def hash(self) -> str:
        """Return the SHA-256 ``journal_hash`` of section 4.3.

        Because a line is exactly what is written to disk, this digest equals the digest of the
        ``journal.jsonl`` bytes once the journal is flushed, which
        ``tests/test_rng_journal.py`` pins against a real file.

        Returns:
            A 64 character lowercase hex digest.
        """
        return journal_hash(self._events)

    # ----------------------------------------------------------------------
    # Context manager
    # ----------------------------------------------------------------------
    def __enter__(self) -> Journal:
        """Return the journal itself, so ``with Journal(...) as journal`` reads well."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the journal, whether the block succeeded or raised."""
        self.close()

    def __repr__(self) -> str:
        """Render the run id, the event count and the destination, never a memory address."""
        return f"Journal(run_id={self._run_id!r}, events={len(self._events)}, path={self._path!r})"


# --------------------------------------------------------------------------------------------------
# Reading, replaying and projecting
# --------------------------------------------------------------------------------------------------
def iter_journal(path: Path, *, validate: bool = True) -> Iterator[JournalEvent]:
    r"""Stream the events of a journal file, validating each one against its schema.

    This is the replay iterator: ``pmx replay`` walks it to rebuild ``results.json`` from the
    journal alone. Reading passes ``newline=JOURNAL_NEWLINE``, which is what makes a CRLF journal
    detectable: universal-newline mode would hand back clean ``"\n"`` lines and the corruption
    would only surface once two machines compared files.

    Args:
        path: The ``journal.jsonl`` file.
        validate: Validate every event against ``journal.v2.json`` (the default). Turn it off only
            for a file this process just wrote and already validated.

    Yields:
        Every event of the file, in file order.

    Raises:
        NonCanonicalValueError: If a line contains a carriage return.
        JournalError: If a line is not a JSON object of a known event type.
        SchemaError: If an event does not validate.
    """
    with open(path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        for index, raw in enumerate(handle):
            _reject_carriage_return(raw, index)
            line = raw.rstrip(JOURNAL_NEWLINE)
            if not line:
                continue
            parsed: object = json.loads(line)
            if not isinstance(parsed, dict):
                raise JournalError("journal line is not a JSON object", path=path.as_posix(), line=index + 1)
            payload = cast("Mapping[str, object]", parsed)
            if validate:
                validate_event_dict(payload)
            yield event_from_dict(payload)


def read_journal(path: Path, *, validate: bool = True) -> tuple[JournalEvent, ...]:
    """Read a whole journal file into events, in file order.

    Args:
        path: The ``journal.jsonl`` file.
        validate: Validate every event against ``journal.v2.json`` (the default).

    Returns:
        Every event of the file, in file order. The ordering guarantees are not checked here; call
        :func:`verify_journal` on the result.

    Raises:
        NonCanonicalValueError: If a line contains a carriage return.
        JournalError: If a line is not a JSON object of a known event type.
        SchemaError: If an event does not validate.
    """
    return tuple(iter_journal(path, validate=validate))


def write_journal(path: Path, events: Sequence[JournalEvent]) -> str:
    """Write events to a file with the journal's own ``open`` arguments and return the hash.

    Used for a journal held in memory (a fixture, a re-serialisation after a read). The envelope
    is not re-checked here: call :func:`verify_journal` first when the events did not come from a
    :class:`Journal`.

    Args:
        path: Destination file. Parent directories are created, an existing file is truncated.
        events: Events in ``seq`` order.

    Returns:
        The SHA-256 hex digest of the bytes just written.

    Raises:
        NonCanonicalValueError: If an event cannot be canonically encoded.
    """
    digest = hashlib.sha256()
    with _open_for_write(path, "w") as handle:
        for event in events:
            line = event_to_line(event)
            handle.write(line)
            digest.update(line.encode(JOURNAL_ENCODING))
    return digest.hexdigest()


def verify_journal(events: Sequence[JournalEvent]) -> None:
    """Raise :class:`~pmx.errors.JournalError` unless the guarantees of section 9.1 all hold.

    The checks are exactly those guarantees and no more, so a journal read halfway through a run
    (no terminal event yet) is still valid:

    1. the journal is not empty;
    2. ``seq`` is ``1, 2, 3, ...`` with no gap and no repeat;
    3. every event carries the same ``run_id``;
    4. ``seq == 1`` is ``run_started`` or ``evolution_started``;
    5. a backtest journal holds no evolution event and an evolution journal no backtest event, so
       ``generation`` never mixes with the bar phases;
    6. every event carries a phase its type allows, and ``bar_ms == 0`` where section 9.1 pins it;
    7. ``bar_ms`` never decreases, and inside one ``bar_ms`` the phase never goes backwards in
       :data:`pmx.types.PHASE_ORDER`;
    8. the terminal event (``run_ended`` or ``evolution_ended``), when present, is the last one;
    9. when both are present, ``run_ended.bar_ms == run_started.t1_ms``.

    Args:
        events: Events in file order.

    Raises:
        JournalError: On any breach, with the seq and the two values that disagree in the context.
    """
    if not events:
        raise JournalError("journal is empty")
    first = events[0]
    run_id = first.run_id
    kind = first.JOURNAL_KIND
    if first.TYPE not in _OPENING_TYPES:
        raise JournalError(
            "seq 1 is run_started or evolution_started (CONTRACTS_V2 section 9.1)",
            run_id=run_id,
            event_type=first.TYPE,
        )
    last_index = len(events) - 1
    previous: JournalEvent | None = None
    for index, event in enumerate(events):
        expected_seq = index + 1
        if event.seq != expected_seq:
            raise JournalError(
                "journal seq must increase by exactly 1",
                run_id=run_id,
                expected_seq=expected_seq,
                actual_seq=event.seq,
                event_type=event.TYPE,
            )
        if event.run_id != run_id:
            raise JournalError(
                "journal mixes two run ids",
                expected_run_id=run_id,
                actual_run_id=event.run_id,
                seq=event.seq,
            )
        if kind != event.JOURNAL_KIND:
            raise JournalError(
                "a journal never mixes a backtest with an evolution (CONTRACTS_V2 section 9.1)",
                run_id=run_id,
                journal_kind=kind,
                seq=event.seq,
                event_type=event.TYPE,
            )
        if event.phase not in event.PHASES:
            raise JournalError(
                "phase is not legal for this event type",
                run_id=run_id,
                seq=event.seq,
                event_type=event.TYPE,
                phase=event.phase,
                phases=",".join(event.PHASES),
            )
        if event.BAR_MS_ZERO and event.bar_ms != 0:
            raise JournalError(
                "this event type carries bar_ms 0 (CONTRACTS_V2 section 9.1)",
                run_id=run_id,
                seq=event.seq,
                event_type=event.TYPE,
                bar_ms=event.bar_ms,
            )
        if previous is not None:
            if event.bar_ms < previous.bar_ms:
                raise JournalError(
                    "journal bar_ms must never decrease",
                    run_id=run_id,
                    seq=event.seq,
                    previous_bar_ms=previous.bar_ms,
                    actual_bar_ms=event.bar_ms,
                )
            if event.bar_ms == previous.bar_ms and PHASE_ORDER.index(event.phase) < PHASE_ORDER.index(previous.phase):
                raise JournalError(
                    "phase must never go backwards inside one bar",
                    run_id=run_id,
                    seq=event.seq,
                    bar_ms=event.bar_ms,
                    previous_phase=previous.phase,
                    actual_phase=event.phase,
                )
        if event.TYPE in _TERMINAL_TYPES and index != last_index:
            raise JournalError(
                "the terminal event is the last event of a journal",
                run_id=run_id,
                seq=event.seq,
                event_type=event.TYPE,
                event_count=len(events),
            )
        previous = event
    if isinstance(first, RunStarted):
        ended = events[last_index]
        if isinstance(ended, RunEnded) and ended.bar_ms != first.t1_ms:
            raise JournalError(
                "run_ended carries bar_ms t1_ms (CONTRACTS_V2 section 9.1)",
                run_id=run_id,
                t1_ms=first.t1_ms,
                actual_bar_ms=ended.bar_ms,
            )


def iter_bars(events: Sequence[JournalEvent]) -> Iterator[tuple[int, tuple[JournalEvent, ...]]]:
    """Group events by ``bar_ms``, ascending, preserving the order inside a bar.

    Exactly one entry per distinct ``bar_ms``, so a consumer cannot see the same bar twice; for a
    journal that respects section 9.1 that is also the file order. ``bar_ms = 0`` (the ``pre``
    events and every evolution event) and ``t1_ms`` (``run_ended``) are ordinary entries here,
    which is what makes them trivially separable in a projection.

    Args:
        events: Events in ``seq`` order.

    Yields:
        ``(bar_ms, events_of_that_bar)`` pairs, ``bar_ms`` ascending.
    """
    grouped: dict[int, list[JournalEvent]] = {}
    for event in events:
        grouped.setdefault(event.bar_ms, []).append(event)
    for bar_ms in sorted(grouped):
        yield bar_ms, tuple(grouped[bar_ms])


def filter_events(events: Sequence[JournalEvent], *types: type[JournalEvent]) -> tuple[JournalEvent, ...]:
    """Keep the events of the given classes, in journal order.

    Args:
        events: Events in ``seq`` order.
        *types: Concrete event classes to keep. With no class given nothing matches and the result
            is empty, never "everything".

    Returns:
        The matching events, order preserved.
    """
    if not types:
        return ()
    kept = tuple(types)
    return tuple(event for event in events if isinstance(event, kept))
