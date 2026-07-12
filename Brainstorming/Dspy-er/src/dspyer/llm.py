from __future__ import annotations

import asyncio
import logging
from typing import Any

import litellm

from .config import get_settings

logger = logging.getLogger(__name__)

litellm.suppress_debug_info = True


class LLMClient:
    """Thin async wrapper around litellm with bounded concurrency and retries."""

    def __init__(self, max_concurrency: int | None = None) -> None:
        settings = get_settings()
        self._semaphore = asyncio.Semaphore(max_concurrency or settings.max_concurrency)
        self._timeout = settings.llm_timeout_seconds
        self._max_retries = settings.llm_max_retries

    async def acomplete(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with self._semaphore:
                    response = await litellm.acompletion(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=self._timeout,
                    )
                content = response.choices[0].message.content
                return content or ""
            except Exception as exc:  # litellm raises provider-specific errors
                last_error = exc
                logger.warning("LLM call failed (attempt %d/%d): %s", attempt + 1, self._max_retries + 1, exc)
                await asyncio.sleep(min(2**attempt, 8))
        raise RuntimeError(f"LLM call to {model} failed after retries: {last_error}") from last_error
