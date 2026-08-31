"""The exception hierarchy (W0).

Engine level errors that the runner catches and turns into journal events. A tool call that trips a
``PermissionDenied`` becomes a ``tool_called`` event with ``ok=false``; it never escapes the runner.
"""

from __future__ import annotations


class AlaError(Exception):
    """Base for every error raised inside the package."""


class KernelError(AlaError):
    """A syscall-like operation failed against the simulated kernel."""


class PermissionDenied(KernelError):
    """The actor lacks the privilege for a vfs or process operation."""


class PathNotFound(KernelError):
    """A vfs path does not exist."""


class InvalidConfigError(AlaError):
    """A match, scenario, or agent was configured with impossible parameters."""


class RngError(AlaError):
    """An unregistered rng substream was requested in strict mode."""


class JournalError(AlaError):
    """A journal could not be written, read, or replayed."""


class ValidationError(AlaError):
    """An agent action or tool call is malformed at the boundary."""
