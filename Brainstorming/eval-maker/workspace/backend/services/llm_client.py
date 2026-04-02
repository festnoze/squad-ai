"""Shared OpenAI client wrapper with JSON mode support."""

import logging

from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError

from backend.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


class LLMClientError(Exception):
    """Raised when an OpenAI API call fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


async def achat_completion(
    system_prompt: str,
    user_message: str,
    response_format: dict | None = None,
) -> str:
    """Wrapper around OpenAI chat completion. Supports JSON mode via response_format.

    Args:
        system_prompt: The system-level instruction.
        user_message: The user-level message.
        response_format: Optional dict like {"type": "json_object"} to enable JSON mode.

    Returns:
        The assistant's response content as a string.

    Raises:
        LLMClientError: If the OpenAI API call fails.
    """
    client = _get_client()

    kwargs: dict = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
    }

    if response_format is not None:
        kwargs["response_format"] = response_format

    logger.info("Calling OpenAI model=%s (json_mode=%s)", settings.openai_model, response_format is not None)

    try:
        response = await client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        return content
    except RateLimitError as exc:
        logger.error("OpenAI rate limit hit: %s", exc)
        raise LLMClientError(f"OpenAI rate limit exceeded: {exc}", status_code=429) from exc
    except APITimeoutError as exc:
        logger.error("OpenAI request timed out: %s", exc)
        raise LLMClientError(f"OpenAI request timed out: {exc}", status_code=504) from exc
    except APIConnectionError as exc:
        logger.error("OpenAI connection error: %s", exc)
        raise LLMClientError(f"OpenAI connection error: {exc}", status_code=502) from exc
    except APIError as exc:
        logger.error("OpenAI API error (status=%s): %s", getattr(exc, "status_code", None), exc)
        raise LLMClientError(
            f"OpenAI API error: {exc}",
            status_code=getattr(exc, "status_code", 500),
        ) from exc


async def achat_completion_messages(
    messages: list[dict],
    response_format: dict | None = None,
) -> str:
    """Chat completion with a full messages list (for multi-turn or complex setups).

    Args:
        messages: Full list of message dicts (role + content).
        response_format: Optional dict for JSON mode.

    Returns:
        The assistant's response content as a string.

    Raises:
        LLMClientError: If the OpenAI API call fails.
    """
    client = _get_client()

    kwargs: dict = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": 0.0,
    }

    if response_format is not None:
        kwargs["response_format"] = response_format

    try:
        response = await client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        return content
    except RateLimitError as exc:
        logger.error("OpenAI rate limit hit: %s", exc)
        raise LLMClientError(f"OpenAI rate limit exceeded: {exc}", status_code=429) from exc
    except APITimeoutError as exc:
        logger.error("OpenAI request timed out: %s", exc)
        raise LLMClientError(f"OpenAI request timed out: {exc}", status_code=504) from exc
    except APIConnectionError as exc:
        logger.error("OpenAI connection error: %s", exc)
        raise LLMClientError(f"OpenAI connection error: {exc}", status_code=502) from exc
    except APIError as exc:
        logger.error("OpenAI API error (status=%s): %s", getattr(exc, "status_code", None), exc)
        raise LLMClientError(
            f"OpenAI API error: {exc}",
            status_code=getattr(exc, "status_code", 500),
        ) from exc
