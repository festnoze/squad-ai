"""Exception hierarchy for Prediction Exchange (pxe).

Every exception derives from :class:`PxeError` and carries a stable, machine
readable ``code`` class attribute. The code is what gets written into the event
journal (``OrderRejected.reason``, ``AgentActionRejected.reason`` ...), so codes
are part of the public contract and must never be renamed silently.

Rules for downstream modules:

* Never raise a bare ``Exception``, ``ValueError`` or ``AssertionError`` from
  library code. Convert to the closest subclass below.
* Never catch :class:`PxeError` broadly inside the engine. The engine is pure
  and synchronous; an unexpected failure must abort the match loudly.
* Only :mod:`pxe.gateway` is allowed to swallow errors, and only to implement
  the "no action" fallback of FR-5.1.1.
"""

from typing import Any

__all__ = [
    "PxeError",
    "ConfigError",
    "InvalidConfigError",
    "UnknownProfileError",
    "DeterminismError",
    "UnknownSubstreamError",
    "NonCanonicalValueError",
    "JournalHashMismatchError",
    "ValidationError",
    "SchemaValidationError",
    "ActionValidationError",
    "ObservationValidationError",
    "ExchangeError",
    "InvalidOrderError",
    "InsufficientCollateralError",
    "OrderLimitExceededError",
    "UnknownOrderError",
    "NotOrderOwnerError",
    "MarketClosedError",
    "AgentFrozenError",
    "AccountingError",
    "InvariantViolationError",
    "EngineError",
    "PhaseOrderError",
    "ReplayMismatchError",
    "GatewayError",
    "AgentTimeoutError",
    "ProviderError",
    "BudgetExceededError",
    "MalformedResponseError",
    "StoreError",
    "TournamentError",
    "HeldoutAccessError",
    "ResumeError",
]


class PxeError(Exception):
    """Root of every Prediction Exchange exception.

    Args:
        message: Human readable description, English only.
        **context: Arbitrary structured context attached to the error and
            echoed in logs. Values must be JSON serialisable.
    """

    code: str = "PXE_ERROR"

    def __init__(self, message: str = "", **context: Any) -> None:
        """Build the error with a message and arbitrary structured context."""
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __str__(self) -> str:
        """Render as ``[CODE] message (key=value, ...)`` with sorted context."""
        if not self.context:
            return f"[{self.code}] {self.message}"
        items = ", ".join(f"{k}={self.context[k]!r}" for k in sorted(self.context))
        return f"[{self.code}] {self.message} ({items})"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON friendly representation used by logs and events."""
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
class ConfigError(PxeError):
    """Base class for configuration problems detected before a match starts."""

    code = "CONFIG_ERROR"


class InvalidConfigError(ConfigError):
    """A config object violates its declared invariants."""

    code = "INVALID_CONFIG"


class UnknownProfileError(ConfigError):
    """An unknown liquidity or information profile name was requested."""

    code = "UNKNOWN_PROFILE"


# --------------------------------------------------------------------------
# Determinism (O1 / AC-P1)
# --------------------------------------------------------------------------
class DeterminismError(PxeError):
    """Base class for any breach of the determinism contract."""

    code = "DETERMINISM_ERROR"


class UnknownSubstreamError(DeterminismError):
    """A random substream name is not part of the declared registry."""

    code = "UNKNOWN_SUBSTREAM"


class NonCanonicalValueError(DeterminismError):
    """A value cannot be canonically serialised into the journal.

    Raised for floats, NaN, sets, and any object without a declared encoding.
    """

    code = "NON_CANONICAL_VALUE"


class JournalHashMismatchError(DeterminismError):
    """Two runs of the same seed produced different journal hashes."""

    code = "JOURNAL_HASH_MISMATCH"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
class ValidationError(PxeError):
    """Base class for schema and payload validation failures."""

    code = "VALIDATION_ERROR"


class SchemaValidationError(ValidationError):
    """A payload failed JSON Schema validation."""

    code = "SCHEMA_INVALID"


class ActionValidationError(ValidationError):
    """An agent action failed semantic validation (FR-6.2.2)."""

    code = "ACTION_INVALID"


class ObservationValidationError(ValidationError):
    """A built observation failed its own schema (engine bug guard)."""

    code = "OBSERVATION_INVALID"


# --------------------------------------------------------------------------
# Exchange
# --------------------------------------------------------------------------
class ExchangeError(PxeError):
    """Base class for order lifecycle failures."""

    code = "EXCHANGE_ERROR"


class InvalidOrderError(ExchangeError):
    """Order fields are out of range or internally inconsistent."""

    code = "INVALID_ORDER"


class InsufficientCollateralError(ExchangeError):
    """Free cash cannot cover the order collateral plus worst case fees."""

    code = "INSUFFICIENT_COLLATERAL"


class OrderLimitExceededError(ExchangeError):
    """The per agent, per market active order cap was reached (FR-5.4.2)."""

    code = "ORDER_LIMIT_EXCEEDED"


class UnknownOrderError(ExchangeError):
    """A cancel referenced an order id that does not exist or is not resting."""

    code = "UNKNOWN_ORDER"


class NotOrderOwnerError(ExchangeError):
    """A cancel referenced an order belonging to another account."""

    code = "NOT_ORDER_OWNER"


class MarketClosedError(ExchangeError):
    """Trading was attempted on a resolved or cancelled market (FR-5.4.5)."""

    code = "MARKET_NOT_OPEN"


class AgentFrozenError(ExchangeError):
    """A bankrupt and frozen agent attempted to trade (FR-5.5.5)."""

    code = "AGENT_FROZEN"


# --------------------------------------------------------------------------
# Accounting
# --------------------------------------------------------------------------
class AccountingError(PxeError):
    """Base class for accounting failures."""

    code = "ACCOUNTING_ERROR"


class InvariantViolationError(AccountingError):
    """A closed system invariant of FR-5.5.3 was violated.

    This is always an engine bug, never an agent behaviour. It must abort the
    match; it must never be downgraded into an integrity incident.
    """

    code = "INVARIANT_VIOLATION"


# --------------------------------------------------------------------------
# Engine / runner
# --------------------------------------------------------------------------
class EngineError(PxeError):
    """Base class for match runner failures."""

    code = "ENGINE_ERROR"


class PhaseOrderError(EngineError):
    """An engine call was made outside of its allowed tick phase."""

    code = "PHASE_ORDER"


class ReplayMismatchError(EngineError):
    """Replaying a journal produced a state different from the recorded one."""

    code = "REPLAY_MISMATCH"


# --------------------------------------------------------------------------
# Agent gateway (the only async surface)
# --------------------------------------------------------------------------
class GatewayError(PxeError):
    """Base class for agent gateway failures."""

    code = "GATEWAY_ERROR"


class AgentTimeoutError(GatewayError):
    """An agent did not answer within its per tick timeout (FR-5.1.1)."""

    code = "AGENT_TIMEOUT"


class ProviderError(GatewayError):
    """The LLM provider returned a non zero exit code or an error payload."""

    code = "PROVIDER_ERROR"


class BudgetExceededError(GatewayError):
    """A per call, per match or per tournament budget cap was reached."""

    code = "BUDGET_EXCEEDED"


class MalformedResponseError(GatewayError):
    """The provider answer could not be parsed into a JSON object."""

    code = "MALFORMED_RESPONSE"


# --------------------------------------------------------------------------
# Store / tournament
# --------------------------------------------------------------------------
class StoreError(PxeError):
    """Persistence layer failure (database or files)."""

    code = "STORE_ERROR"


class TournamentError(PxeError):
    """Base class for orchestration failures."""

    code = "TOURNAMENT_ERROR"


class HeldoutAccessError(TournamentError):
    """A held-out scenario bank was accessed outside of an evaluation run."""

    code = "HELDOUT_ACCESS"


class ResumeError(TournamentError):
    """A tournament could not be resumed without double counting matches."""

    code = "RESUME_ERROR"
