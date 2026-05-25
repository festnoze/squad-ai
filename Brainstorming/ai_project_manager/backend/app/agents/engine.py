"""Agent engine abstraction.

Separates "how the LLM is invoked" (which framework, which provider,
which prompt schema) from "what the agent does" (build messages, parse
response, act on the result). The rest of the codebase only knows
`AgentEngine.ainvoke_json(...)` and does not care whether the
underlying call went through common-tools, Google ADK, or a mock.

Why the abstraction instead of a direct `Llm.ainvoke` call?

- The user asked for ADK but does not yet have a Google API key. Shipping
  V1 with a feature flag lets them swap implementations later without
  touching agent code.
- Tests need a deterministic implementation with no network calls. A
  `MockAgentEngine` is injected via `app.agents.engine.set_engine(...)`
  and returns hard-coded payloads.

Engine selection: `AGENT_ENGINE` environment variable, read lazily at
first call. Valid values: `fallback` (default, uses common-tools) and
`adk` (not implemented yet — raises a descriptive error).
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class AgentEngine(ABC):
    """Contract every agent engine must implement."""

    @abstractmethod
    async def ainvoke_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[Any] | None = None,
        action_name: str = "agent_engine.ainvoke_json",
    ) -> dict[str, Any]:
        """Call the underlying LLM with a system prompt + user prompt.

        The response must be a parsed JSON dict. If ``schema`` is
        provided, implementations should validate against it (for
        engines that support structured output parsing); otherwise the
        engine is expected to extract the JSON payload from the raw
        response by itself.
        """


class CommonToolsAgentEngine(AgentEngine):
    """Default engine backed by `common_tools.llm.Llm.ainvoke`.

    Uses the same LLM instance as the scoping chat (via `get_llm()`),
    which means the agent provider is configured through the existing
    `LLM_INFO` env var. Works out of the box for every user who already
    has the chat feature working.
    """

    async def ainvoke_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[Any] | None = None,
        action_name: str = "agent_engine.ainvoke_json",
    ) -> dict[str, Any]:
        # Lazy imports: common-tools may not be present in lightweight
        # test environments, and we want `set_engine(MockAgentEngine())`
        # to keep working even then.
        from common_tools.llm.llm_helper import Llm
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.services.llm_factory import get_llm

        llm = get_llm()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        parser: Any = None
        if schema is not None:
            try:
                from common_tools.llm.extracted_json_output_parser import (
                    ExtractedJsonOutputParser,
                )
                parser = ExtractedJsonOutputParser(pydantic_object=schema)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Could not build ExtractedJsonOutputParser, falling "
                    "back to raw JSON extraction",
                    exc_info=True,
                )

        response = await Llm.ainvoke(
            llm_or_llms=llm,
            prompt_or_prompts=messages,
            parser=parser,
            action_name=action_name,
        )

        # Normalise common-tools return types to a single dict.
        if isinstance(response, list):
            response = response[0] if response else {}
        if isinstance(response, dict):
            return response
        if isinstance(response, str):
            return _extract_json_from_text(response)
        # Some LangChain runnables return a message-like object.
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return _extract_json_from_text(content)
        raise TypeError(
            f"Unsupported agent engine response type: {type(response).__name__}",
        )


class AdkAgentEngine(AgentEngine):
    """Placeholder for the Google ADK backend.

    Not implemented yet: the user does not have a Google API key at
    install time. When they do, this class should delegate to
    `google.adk.agents.LlmAgent` (or equivalent) and call its run loop.
    """

    async def ainvoke_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[Any] | None = None,
        action_name: str = "agent_engine.ainvoke_json",
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "ADK agent engine is not wired yet. Install google-adk, set "
            "GOOGLE_API_KEY in your .env, and implement this class. "
            "In the meantime, use AGENT_ENGINE=fallback (the default).",
        )


def _extract_json_from_text(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction from a free-form LLM response.

    Handles the common "the model wrapped its JSON in ```json ... ```"
    case by locating the first `{` and matching the final `}`. Returns
    an empty dict if no JSON object can be found, which lets calling
    agents decide how to handle the failure.
    """
    if not text:
        return {}
    stripped = text.strip()
    # Fast path: already pure JSON.
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    candidate = stripped[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Module-level singleton with test override support
# ---------------------------------------------------------------------------


_engine: AgentEngine | None = None


def get_engine() -> AgentEngine:
    """Return the configured agent engine, building it on first access."""
    global _engine
    if _engine is not None:
        return _engine
    choice = (os.environ.get("AGENT_ENGINE") or "fallback").lower()
    if choice == "adk":
        _engine = AdkAgentEngine()
    else:
        _engine = CommonToolsAgentEngine()
    return _engine


def set_engine(engine: AgentEngine | None) -> None:
    """Override the engine (tests). Pass ``None`` to reset to default."""
    global _engine
    _engine = engine
