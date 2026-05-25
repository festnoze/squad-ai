"""Thin wrapper around the `common-tools` LangChainFactory.

Reads the `LLM_INFO` dict from settings, converts it to an `LlmInfo`, and
returns a cached `Runnable` (LangChain LLM) ready to be passed to
`Llm.ainvoke(...)`.

The key is read from `OPENAI_API_KEY` (or equivalent provider-specific env
vars) by common-tools itself; we don't pass it explicitly. Missing / invalid
credentials raise a `LlmNotConfiguredError` the first time the factory is
called, but the app keeps booting (the CRUD endpoints still work).
"""

import logging
from functools import lru_cache
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


class LlmNotConfiguredError(RuntimeError):
    """Raised when `get_llm()` is called without a usable LLM configuration."""


@lru_cache
def get_llm() -> Any:
    """Return a cached LangChain Runnable for the configured LLM.

    Raises:
        LlmNotConfiguredError: If `LLM_INFO` or the provider key is missing,
            or if common-tools fails to construct the Runnable.
    """
    settings = get_settings()
    llm_info_dict: dict[str, Any] = settings.llm_info

    if not llm_info_dict or "type" not in llm_info_dict or "model" not in llm_info_dict:
        logger.warning(
            "LLM_INFO is missing or incomplete — LLM features are disabled"
        )
        raise LlmNotConfiguredError(
            "LLM_INFO is missing or malformed. Add it to your .env file."
        )

    # Imported lazily so the app can still boot if common-tools is not yet
    # installed (the CRUD endpoints don't depend on the LLM stack).
    try:
        from common_tools.llm.langchain_factory import LangChainFactory
        from common_tools.models.llm_info import LlmInfo
    except ImportError as exc:
        logger.warning("common-tools is not installed: %s", exc)
        raise LlmNotConfiguredError(
            "common-tools is not installed. See start.md for the editable install "
            "step using COMMONTOOLS_LOCAL_PATH."
        ) from exc

    try:
        llm_info = LlmInfo.factory_from_dict(llm_info_dict)
        llm = LangChainFactory.create_llm_from_info(llm_info)
    except Exception as exc:
        logger.exception("Failed to instantiate LLM from LLM_INFO: %s", llm_info_dict)
        raise LlmNotConfiguredError(
            f"Could not build LLM from LLM_INFO={llm_info_dict}: {exc}"
        ) from exc

    logger.info(
        "Instantiated LLM via common-tools: type=%s model=%s",
        llm_info_dict.get("type"),
        llm_info_dict.get("model"),
    )
    return llm
