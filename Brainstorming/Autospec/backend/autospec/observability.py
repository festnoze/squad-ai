"""Optional Langfuse tracing of agent calls (O1).

Env-gated (``AUTOSPEC_LANGFUSE``) and lazily imported: when langfuse is not
installed or not configured, every entry point is a no-op. Tracing must NEVER
affect the pipeline, so all langfuse interaction is wrapped — a failure here is
logged and swallowed, never raised. The client reads LANGFUSE_PUBLIC_KEY /
LANGFUSE_SECRET_KEY / LANGFUSE_HOST from the environment itself.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

_client: Any = None
_init_attempted = False


def _client_or_none() -> Any:
    """Lazily build the Langfuse client once, or return None when tracing is
    disabled / langfuse is unavailable / misconfigured."""
    global _client, _init_attempted
    if _init_attempted:
        return _client
    _init_attempted = True
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse import Langfuse  # lazy: optional dependency
        _client = Langfuse()
    except Exception as exc:  # noqa: BLE001 — not installed or bad config
        logger.warning("Langfuse tracing disabled (%s)", exc)
        _client = None
    return _client


def reset() -> None:
    """Drop the cached client so the next call re-reads settings (used by tests)."""
    global _client, _init_attempted
    _client = None
    _init_attempted = False


def trace_agent_call(
    *,
    name: str,
    model: str,
    input_text: str,
    output_text: str,
    metadata: dict,
    cost_usd: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    duration_ms: int = 0,
) -> None:
    """Record one agent call as a Langfuse generation. Best-effort; never raises."""
    client = _client_or_none()
    if client is None:
        return
    try:
        gen = getattr(client, "generation", None) or getattr(client, "start_generation", None)
        if gen is None:
            return
        obj = gen(
            name=name,
            model=model,
            input=input_text,
            output=output_text,
            metadata={
                **metadata,
                "cost_usd": cost_usd,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "duration_ms": duration_ms,
            },
            usage_details={"input": input_tokens, "output": output_tokens},
        )
        end = getattr(obj, "end", None)
        if callable(end):
            end()  # v3 span-like objects must be ended; v2 no-ops here
        flush = getattr(client, "flush", None)
        if callable(flush):
            flush()
    except Exception as exc:  # noqa: BLE001 — tracing must never break the pipeline
        logger.warning("Langfuse trace failed (%s)", exc)
