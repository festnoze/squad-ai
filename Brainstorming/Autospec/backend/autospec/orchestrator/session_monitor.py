"""Claude usage-window watchdog (M2).

When the Claude Code harness reports an exhausted usage window (the
subscription's 5-hour billing block), the pipeline stops cleanly and schedules
an automatic resume at the moment a fresh session window opens. The reset time
comes from, in order:

1. the epoch sometimes embedded in the CLI error (``…limit reached|<epoch>``) ;
2. the active billing block reported by **ccusage** (``ccusage blocks --json``),
   which reads the local Claude Code usage data ;
3. a fallback delay (``AUTOSPEC_RESUME_FALLBACK_MIN``) — if the window is still
   exhausted at resume time, the watchdog simply reschedules.

Compliance note: this is legitimate scheduling of the user's own subscription
(no limit bypass, no account multiplexing) — the work just WAITS for the window
to reset, exactly like a manual retry would, so the subscribed quota is used
instead of being lost.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import time
from datetime import datetime

from ..config import settings

logger = logging.getLogger(__name__)

# Messages the Claude CLI emits when the subscription usage window is exhausted.
_LIMIT_RE = re.compile(
    r"usage limit reached|reached your usage limit|limit reached\|\d|5-hour limit",
    re.IGNORECASE,
)

# "Claude AI usage limit reached|1718226000" — epoch (s or ms) after a pipe.
_RESET_EPOCH_RE = re.compile(r"\|(\d{9,13})\b")


def monitor_active() -> bool:
    """The watchdog only concerns the real Claude harness (subscription)."""
    return (
        settings.session_monitor_enabled
        and settings.agent_provider == "claude"
        and not settings.fake_agents
    )


def is_usage_limit_error(text: str) -> bool:
    return bool(_LIMIT_RE.search(text))


def parse_reset_epoch(text: str) -> float | None:
    """Epoch embedded in the CLI error message, normalized to seconds."""
    match = _RESET_EPOCH_RE.search(text)
    if not match:
        return None
    value = float(match.group(1))
    return value / 1000 if value > 1e12 else value


def parse_blocks(payload: dict) -> float | None:
    """End time (epoch) of the ACTIVE billing block in a `ccusage blocks --json`
    payload — i.e. when a fresh session window opens. None when unavailable."""
    for block in payload.get("blocks") or []:
        if not isinstance(block, dict) or not block.get("isActive"):
            continue
        end = block.get("endTime")
        if not end:
            continue
        try:
            return datetime.fromisoformat(str(end).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


async def aget_block_reset() -> float | None:
    """Ask ccusage for the active block's end time. Best-effort: any failure
    (tool missing, bad JSON, no active block) returns None."""

    def _run() -> float | None:
        try:
            proc = subprocess.run(
                f"{settings.ccusage_cmd} blocks --json",
                shell=True,  # resolves npx.cmd/ccusage.cmd on Windows
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            if proc.returncode != 0 or not proc.stdout:
                return None
            return parse_blocks(json.loads(proc.stdout))
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            logger.warning("ccusage indisponible : %s", exc)
            return None

    return await asyncio.to_thread(_run)


async def anext_reset(error_text: str) -> float:
    """Best estimate of when a fresh session window opens (epoch, future)."""
    at = parse_reset_epoch(error_text)
    if at is None:
        at = await aget_block_reset()
    now = time.time()
    if at is None or at <= now:
        at = now + settings.resume_fallback_min * 60
    return at
