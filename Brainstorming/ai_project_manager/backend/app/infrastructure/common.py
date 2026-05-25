"""Infrastructure-level utilities shared across entities, repositories and
services.

Keep this module intentionally small — it exists to break small duplications
that pop up in multiple layers (e.g. a "current UTC datetime" helper).
"""

from datetime import datetime, timezone


def get_utc_now() -> datetime:
    """Return the current UTC datetime as a timezone-aware object.

    Preferred over :func:`datetime.utcnow` (deprecated in Python 3.12+) and
    over inlining the call site so that every layer producing a timestamp
    agrees on the exact semantics (always UTC, always timezone-aware).
    """
    return datetime.now(timezone.utc)
