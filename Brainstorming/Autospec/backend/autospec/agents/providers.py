"""LangChain agent backends: OpenAI (API key) and Ollama (local models).

Off-subscription providers are driven through LangChain chat models
(``langchain-openai`` / ``langchain-ollama``), unlike Claude which goes through
the Claude Code CLI harness. Two gaps with the CLI harness are bridged here:

- Sessions: chat models are stateless, so multi-turn continuity (the PM
  interview resumes a session) is kept in-memory per session id and replayed
  each call.
- Files: agents that must edit the workspace (Dev) use a bounded JSON tool
  protocol — the model replies ``{"tool": "write_files"|"read_files", ...}``
  for at most ``settings.provider_tool_rounds`` rounds, then gives its final
  answer. Paths are confined to the working directory.

The orchestrator independently re-verifies with pytest, so a model that cannot
run commands itself still fits the pipeline.
"""

from __future__ import annotations

import json
import uuid
import asyncio
from pathlib import Path

from ..config import settings
from .file_broker import FILE_PROTOCOL, FileBroker, IsolationViolation, context_for, active_dependency_handler, active_claim_handler
from .runner import (
    AgentError,
    AgentResult,
    AgentRunner,
    ClaudeCliRunner,
    CodexCliRunner,
    RunnerCapabilities,
    extract_json,
    observe_provider,
)

TOOL_PROTOCOL = FILE_PROTOCOL

_MAX_READ_CHARS = 30_000


def _safe_path(cwd: Path, rel: str) -> Path:
    """Resolve ``rel`` inside ``cwd``; AgentError on traversal attempts."""
    try:
        return FileBroker(context_for(cwd)).path(rel)
    except IsolationViolation as exc:
        raise AgentError(str(exc), code=exc.code) from exc


def _apply_tool(cwd: Path, call: dict) -> str:
    """Execute one read_files/write_files tool call; return the textual result."""
    try:
        return FileBroker(context_for(cwd)).apply(call)
    except IsolationViolation as exc:
        raise AgentError(str(exc), code=exc.code) from exc


def _content_text(content) -> str:
    """Normalize a LangChain message content (str or content blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


class _LangChainRunner:
    """Shared LangChain chat runner: session replay + bounded file tool loop.

    Subclasses implement ``_build_model()`` returning a LangChain chat model
    (``BaseChatModel``); the import happens lazily so the backend stays
    importable when the provider's package is not installed.
    """

    reports_provider_turns = True

    def __init__(self) -> None:
        self._sessions: dict[str, list] = {}  # session id -> LangChain messages
        self._model = None

    # ------------------------------------------------------------ subclass API

    def _build_model(self):  # pragma: no cover - overridden
        raise NotImplementedError

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0

    # ------------------------------------------------------------- chat call

    async def _achat(self, messages: list) -> tuple[str, int, int]:
        """One model turn -> (text, input_tokens, output_tokens)."""
        if self._model is None:
            self._model = self._build_model()
        try:
            response = await self._model.ainvoke(messages)
        except Exception as exc:  # network, auth, model errors — LangChain-specific
            raise AgentError(f"Appel LLM (LangChain) échoué : {exc}")
        usage = getattr(response, "usage_metadata", None) or {}
        return (
            _content_text(response.content),
            int(usage.get("input_tokens", 0) or 0),
            int(usage.get("output_tokens", 0) or 0),
        )

    # ---------------------------------------------------------------- arun

    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        except ImportError:
            raise AgentError(
                "LangChain n'est pas installé (uv sync) — requis pour ce provider."
            )
        sid = session_id or f"lc-{uuid.uuid4().hex[:12]}"
        history = list(self._sessions.get(sid, []))
        system = system_prompt + (TOOL_PROTOCOL if cwd is not None else "")
        messages = [SystemMessage(content=system), *history, HumanMessage(content=prompt)]
        total_in = total_out = 0
        text = ""
        for _ in range(settings.provider_tool_rounds):
            await observe_provider(True)
            try:
                text, n_in, n_out = await self._achat(messages)
            finally:
                await observe_provider(False)
            total_in += n_in
            total_out += n_out
            messages.append(AIMessage(content=text))
            if cwd is None:
                break
            try:
                call = extract_json(text)
            except AgentError:
                break  # not JSON at all: final (prose) answer
            if "tool" not in call:
                break  # final answer
            if call["tool"] in {"dependency_request", "claim_expand"}:
                handler = (active_dependency_handler.get() if call["tool"] == "dependency_request"
                           else active_claim_handler.get())
                if handler is None:
                    raise AgentError("DEPENDENCY_COORDINATOR_UNAVAILABLE: no trusted dependency handler",
                                     code="DEPENDENCY_COORDINATOR_UNAVAILABLE")
                context = context_for(cwd)
                request = {key: value for key, value in call.items() if key not in {"tool", "task_id"}}
                if context.task_id:
                    request["task_id"] = context.task_id
                result = json.dumps(await asyncio.to_thread(handler, cwd, request), ensure_ascii=False)
            else:
                result = await asyncio.to_thread(_apply_tool, cwd, call)
            messages.append(HumanMessage(content=f"Résultat de l'outil :\n{result}"))
        else:
            # Tool-round cap reached with the model still asking for tools.
            raise AgentError(
                f"L'agent n'a pas conclu en {settings.provider_tool_rounds} tours d'outils."
            )
        self._sessions[sid] = messages[1:]  # replayed next turn (minus system)
        return AgentResult(
            text=text,
            session_id=sid,
            cost_usd=self._cost(total_in, total_out),
            input_tokens=total_in,
            output_tokens=total_out,
        )


class OpenAiRunner(_LangChainRunner):
    """OpenAI (or any OpenAI-compatible endpoint) via langchain-openai."""

    name = "openai"

    def _build_model(self):
        if not settings.openai_api_key:
            raise AgentError(
                "Clé API OpenAI absente (OPENAI_API_KEY)."
            )
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise AgentError(
                "langchain-openai n'est pas installé (uv sync) — requis pour le provider openai."
            )
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.agent_timeout_s,
        )

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * settings.openai_price_in
            + output_tokens * settings.openai_price_out
        ) / 1_000_000


# How many top programming models OpenRouter's selector shows (live discovery).
OPENROUTER_PROGRAMMING_LIMIT = 10

# Static fallback shown only when live discovery is unavailable (offline / no key).
# The real list comes from GET {base}/models?category=programming (most-popular).
OPENROUTER_FALLBACK_MODELS: tuple[str, ...] = (
    "anthropic/claude-sonnet-4",
    "anthropic/claude-opus-4",
    "openai/gpt-5",
    "openai/gpt-4.1",
    "google/gemini-2.5-pro",
    "deepseek/deepseek-chat",
    "qwen/qwen3-coder",
    "x-ai/grok-code-fast-1",
    "moonshotai/kimi-k2",
    "z-ai/glm-4.6",
)


class OpenRouterRunner(_LangChainRunner):
    """OpenRouter (OpenAI-compatible aggregator hub) via langchain-openai.

    Same chat/file-tool loop as OpenAI; only the endpoint, key and model differ.
    OpenRouter recommends the X-Title / HTTP-Referer headers for attribution."""

    name = "openrouter"

    def _build_model(self):
        if not settings.openrouter_api_key:
            raise AgentError(
                "Clé API OpenRouter absente (OPENROUTER_API_KEY)."
            )
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise AgentError(
                "langchain-openai n'est pas installé (uv sync) — requis pour le provider openrouter."
            )
        return ChatOpenAI(
            model=settings.openrouter_model or OPENROUTER_FALLBACK_MODELS[0],
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            timeout=settings.agent_timeout_s,
            default_headers={"X-Title": "Autospec", "HTTP-Referer": "https://github.com/autospec"},
        )

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * settings.openrouter_price_in
            + output_tokens * settings.openrouter_price_out
        ) / 1_000_000


class OllamaRunner(_LangChainRunner):
    """Local models through Ollama via langchain-ollama (no key, zero cost)."""

    name = "ollama"

    def _build_model(self):
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            raise AgentError(
                "langchain-ollama n'est pas installé (uv sync) — requis pour le provider ollama."
            )
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
        )


class AnthropicRunner(_LangChainRunner):
    """Anthropic Claude via the API directly (langchain-anthropic), independent
    of the local Claude Code CLI harness."""

    name = "anthropic"

    def _build_model(self):
        if not settings.anthropic_api_key:
            raise AgentError(
                "Clé API Anthropic absente (ANTHROPIC_API_KEY)."
            )
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise AgentError(
                "langchain-anthropic n'est pas installé (uv sync) — requis pour le provider anthropic."
            )
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            timeout=settings.agent_timeout_s,
        )

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * settings.anthropic_price_in
            + output_tokens * settings.anthropic_price_out
        ) / 1_000_000


# "claude code" is first (the default provider): the Claude Code CLI harness
# (subscription). "claude" is the Anthropic API (direct, key-based). codex/
# openai/openrouter/ollama follow.
PROVIDERS = ("claude code", "claude", "codex", "openai", "openrouter", "ollama")

# Suggested models per provider, shown in the UI's second (adaptive) dropdown.
# These are display/endpoint values passed straight to the backend, so a user
# can still configure another one via the *_MODEL env vars — the active
# model is always injected into the list so the selection round-trips correctly.
MODEL_CHOICES: dict[str, tuple[str, ...]] = {
    # The Codex CLI runs OpenAI models; these are suggestions (env/live-discovery
    # can override). Empty model = the codex CLI default.
    "codex": ("gpt-5.3-codex", "gpt-5.4-codex", "o4-mini"),
    # The Claude Code CLI accepts full model ids (and short aliases like "opus").
    # Static fallback only — the live list comes from the Anthropic /v1/models
    # endpoint when an ANTHROPIC_API_KEY is configured (see agents/discovery.py).
    "claude code": (
        "claude-opus-5",
        "claude-fable-5",
        "claude-sonnet-5",
        "claude-haiku-4-5",
    ),
    # Anthropic API ("claude") accepts the same ids (aliases resolve server-side).
    "claude": (
        "claude-opus-5",
        "claude-fable-5",
        "claude-sonnet-5",
        "claude-haiku-4-5",
    ),
    "openai": (
        "gpt-4.1",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        "gpt-5.3-codex",
        "gpt-4o-mini",
    ),
    "ollama": ("llama3.1", "qwen3", "mistral", "deepseek-r1"),
    # Fallback only — the live list is the most-popular programming models from
    # OpenRouter (GET {base}/models?category=programming), fetched on demand.
    "openrouter": OPENROUTER_FALLBACK_MODELS,
}


def provider_models(provider: str) -> list[str]:
    """Suggested model choices for a provider, with the active one included.

    The currently configured model is always present (prepended if missing) so
    the UI dropdown can reflect a non-default model set via env vars."""
    choices = list(MODEL_CHOICES.get(provider, ()))
    current = provider_model(provider)
    # A "(défaut …)" placeholder is not a real selectable model id.
    if current and not current.startswith("(défaut") and current not in choices:
        choices.insert(0, current)
    return choices


def provider_capabilities(provider: str) -> RunnerCapabilities:
    """Static capability contract for each provider family.

    The orchestrator can still verify tests for every provider; this tells the
    UI/operator which backends can inspect/run the workspace themselves versus
    the bounded LangChain file-tool protocol.
    """
    normalized = (provider or "claude code").strip().lower()
    if normalized == "claude code":
        return RunnerCapabilities(
            can_edit_files=True,
            can_run_shell=False,
            supports_native_skills=False,
            reliable_for_build=True,
            execution_model="restricted_tools",
            notes="Claude Code abonnement: outils natifs, shell, MCP et skills désactivés; fichiers médiés et tests isolés par Autospec.",
        )
    if normalized == "codex":
        return RunnerCapabilities(
            can_edit_files=False,
            can_run_shell=False,
            supports_native_skills=False,
            reliable_for_build=False,
            execution_model="unavailable",
            notes="ISOLATION_UNAVAILABLE: backend Codex à shell hôte désactivé; aucune exécution sans frontière prouvée.",
        )
    if normalized in ("openai", "openrouter", "ollama", "claude", "anthropic"):
        return RunnerCapabilities(
            can_edit_files=True,
            can_run_shell=False,
            supports_native_skills=False,
            reliable_for_build=False,
            execution_model="langchain_file_tools",
            notes="Provider LangChain: lecture/écriture de fichiers seulement; tests et commandes lancés par Autospec.",
        )
    if normalized == "fake":
        return RunnerCapabilities(
            can_edit_files=False,
            can_run_shell=False,
            supports_native_skills=False,
            reliable_for_build=False,
            execution_model="scripted",
            notes="Mode démonstration déterministe.",
        )
    return RunnerCapabilities(
        can_edit_files=False,
        can_run_shell=False,
        supports_native_skills=False,
        reliable_for_build=False,
        execution_model="unknown",
        notes=f"Provider inconnu: {provider}",
    )


def make_runner(provider: str) -> AgentRunner:
    """Build the agent backend for a provider name (AGENT_PROVIDER)."""
    normalized = (provider or "claude code").strip().lower()
    if settings.generation_only_agents:
        if normalized not in ("", "claude code"):
            raise ValueError("GENERATION_ONLY: seul Claude Code abonnement est autorisé, pas une API directe.")
        from .generation_policy import GenerationOnlyRunner
        return GenerationOnlyRunner(ClaudeCliRunner(), model="sonnet")
    if normalized == "openai":
        return OpenAiRunner()
    if normalized == "openrouter":
        return OpenRouterRunner()
    if normalized == "ollama":
        return OllamaRunner()
    # "claude" = the Anthropic API direct ("anthropic" kept as a legacy alias).
    if normalized in ("claude", "anthropic"):
        return AnthropicRunner()
    if normalized == "codex":
        return CodexCliRunner()
    # "claude code" = the Claude Code CLI harness (subscription), the default.
    if normalized in ("", "claude code"):
        return ClaudeCliRunner()
    raise ValueError(f"Provider inconnu : {provider!r} (attendu : {', '.join(PROVIDERS)})")


def provider_model(provider: str) -> str:
    """The model currently configured for a provider (display/endpoint)."""
    if provider == "openai":
        return settings.openai_model
    if provider == "openrouter":
        return settings.openrouter_model or "(défaut OpenRouter)"
    if provider == "ollama":
        return settings.ollama_model
    if provider in ("claude", "anthropic"):
        return settings.anthropic_model
    if provider == "codex":
        return settings.codex_model or "(défaut Codex CLI)"
    return settings.claude_model or "(défaut CLI)"
