"""Live model discovery per provider.

Shows the models that are *actually reachable* in the model selector instead of a
static guess:

- ``ollama``  : the Ollama HTTP API ``GET {base_url}/api/tags`` (the programmatic
  equivalent of ``ollama list``) — the models really pulled on the configured
  Ollama server.
- ``openai``  : ``GET {base_url}/models`` with the API key — the models the key
  can actually access (filtered to chat-capable ids).
- ``codex``   : reuses the OpenAI catalogue (the Codex CLI runs OpenAI models).
- ``claude`` / ``anthropic`` : static choices (no public list endpoint / the CLI
  exposes only aliases).

All network/subprocess work runs in a worker thread (the event loop on Windows is
a SelectorEventLoop). Callers fall back to the static ``provider_models`` list on
failure, so discovery is best-effort and never blocks the UI.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

from ..config import settings
from .providers import OPENROUTER_PROGRAMMING_LIMIT, provider_models

# Discovery network calls are short; keep them snappy so the selector stays live.
_DISCOVERY_TIMEOUT_S = 6

# OpenAI returns every model (embeddings, audio, image…). Keep only chat-capable
# ids and drop the obvious non-chat families.
_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt")
_NON_CHAT_MARKERS = (
    "embedding", "whisper", "tts", "audio", "dall-e", "image", "realtime",
    "moderation", "search", "transcribe", "codex-mini",
)


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    """Blocking GET returning parsed JSON (run via asyncio.to_thread)."""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=_DISCOVERY_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _discover_ollama_sync() -> list[str]:
    data = _http_get_json(f"{settings.ollama_base_url}/api/tags")
    models = data.get("models") or []
    names = [str(m.get("name") or "").strip() for m in models if isinstance(m, dict)]
    return sorted(n for n in names if n)


def _is_chat_model(model_id: str) -> bool:
    low = model_id.lower()
    if any(marker in low for marker in _NON_CHAT_MARKERS):
        return False
    return low.startswith(_CHAT_PREFIXES)


def _discover_openai_sync() -> list[str]:
    if not settings.openai_api_key:
        raise RuntimeError("clé API OpenAI absente")
    data = _http_get_json(
        f"{settings.openai_base_url}/models",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
    )
    ids = [str(m.get("id") or "").strip() for m in (data.get("data") or []) if isinstance(m, dict)]
    chat = sorted({i for i in ids if i and _is_chat_model(i)})
    return chat or sorted(i for i in ids if i)


def _discover_openrouter_sync() -> list[str]:
    """The most-popular programming models on OpenRouter, top
    ``OPENROUTER_PROGRAMMING_LIMIT`` — ``GET {base}/models?category=programming``
    (the API behind https://openrouter.ai/models?categories=programming&order=most-popular),
    already returned in popularity order for that category."""
    headers = {}
    if settings.openrouter_api_key:
        headers["Authorization"] = f"Bearer {settings.openrouter_api_key}"
    data = _http_get_json(
        f"{settings.openrouter_base_url}/models?category=programming", headers=headers
    )
    ids = [str(m.get("id") or "").strip() for m in (data.get("data") or []) if isinstance(m, dict)]
    top = [i for i in ids if i][:OPENROUTER_PROGRAMMING_LIMIT]
    if not top:
        raise RuntimeError("aucun modèle OpenRouter renvoyé")
    return top


async def adiscover_models(provider: str) -> tuple[list[str], str]:
    """Return ``(models, source)`` for a provider. ``source`` is ``"live"`` when
    discovery succeeded, else ``"static"`` (the suggested fallback list).

    Never raises: any failure degrades to the static list so the selector keeps
    working offline / without a key / when the daemon is down."""
    p = (provider or "").strip().lower()
    try:
        if p == "ollama":
            return (await asyncio.to_thread(_discover_ollama_sync)), "live"
        if p == "openai":
            return (await asyncio.to_thread(_discover_openai_sync)), "live"
        if p == "openrouter":
            return (await asyncio.to_thread(_discover_openrouter_sync)), "live"
        if p == "codex":
            # Codex runs OpenAI models — reuse the OpenAI catalogue when a key is
            # configured, else fall back to the static codex suggestions.
            return (await asyncio.to_thread(_discover_openai_sync)), "live"
    except (urllib.error.URLError, OSError, ValueError, RuntimeError):
        pass
    return provider_models(p), "static"
