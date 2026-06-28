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
from pathlib import Path

from ..config import settings
from .runner import (
    AgentError,
    AgentResult,
    AgentRunner,
    ClaudeCliRunner,
    CodexCliRunner,
    RunnerCapabilities,
    extract_json,
)

TOOL_PROTOCOL = """

--- FILE TOOL PROTOCOL (HIGHEST PRIORITY) ---
You cannot run shell commands. To work on the project files of the current
working directory, reply with EXACTLY ONE JSON object per turn:
- {"tool": "read_files", "paths": ["relative/path.py", "..."]}
- {"tool": "write_files", "files": [{"path": "relative/path.py", "content": "<full file content>"}]}
The orchestrator executes the tool and sends you the result; then continue.
When (and only when) you are done with the files, reply with the FINAL JSON
object the task asked for (it must NOT contain a "tool" key). Never run tests
yourself: the orchestrator runs pytest after you.
"""

_MAX_READ_CHARS = 30_000


def _safe_path(cwd: Path, rel: str) -> Path:
    """Resolve ``rel`` inside ``cwd``; AgentError on traversal attempts."""
    target = (cwd / rel).resolve()
    if not target.is_relative_to(cwd.resolve()):
        raise AgentError(f"Chemin hors du workspace refusé : {rel!r}")
    return target


def _apply_tool(cwd: Path, call: dict) -> str:
    """Execute one read_files/write_files tool call; return the textual result."""
    tool = call.get("tool")
    if tool == "write_files":
        written = []
        for item in call.get("files") or []:
            rel = str(item.get("path") or "")
            if not rel:
                continue
            target = _safe_path(cwd, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(item.get("content") or ""), encoding="utf-8")
            written.append(rel)
        return f"OK — fichiers écrits : {json.dumps(written, ensure_ascii=False)}"
    if tool == "read_files":
        chunks = []
        for rel in call.get("paths") or []:
            target = _safe_path(cwd, str(rel))
            if not target.is_file():
                chunks.append(f"--- {rel} ---\n(fichier introuvable)")
                continue
            content = target.read_text(encoding="utf-8", errors="replace")[:_MAX_READ_CHARS]
            chunks.append(f"--- {rel} ---\n{content}")
        return "\n".join(chunks) or "(aucun fichier demandé)"
    raise AgentError(f"Outil inconnu demandé par l'agent : {tool!r}")


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
            text, n_in, n_out = await self._achat(messages)
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
            result = _apply_tool(cwd, call)
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
                "Clé API OpenAI absente (AUTOSPEC_OPENAI_API_KEY ou OPENAI_API_KEY)."
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
                "Clé API OpenRouter absente (AUTOSPEC_OPENROUTER_API_KEY ou OPENROUTER_API_KEY)."
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
                "Clé API Anthropic absente (AUTOSPEC_ANTHROPIC_API_KEY ou ANTHROPIC_API_KEY)."
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


# Claude is first (the default provider): the UI lists it first and selects it by
# default. codex/openai/openrouter/ollama/anthropic follow.
PROVIDERS = ("claude", "codex", "openai", "openrouter", "ollama", "anthropic")

# Suggested models per provider, shown in the UI's second (adaptive) dropdown.
# These are display/endpoint values passed straight to the backend, so a user
# can still configure another one via the AUTOSPEC_*_MODEL env vars — the active
# model is always injected into the list so the selection round-trips correctly.
MODEL_CHOICES: dict[str, tuple[str, ...]] = {
    # The Codex CLI runs OpenAI models; these are suggestions (env/live-discovery
    # can override). Empty model = the codex CLI default.
    "codex": ("gpt-5.3-codex", "gpt-5.4-codex", "o4-mini"),
    # The Claude Code CLI accepts short aliases.
    "claude": ("opus", "sonnet", "haiku"),
    # Anthropic API needs the full model ids.
    "anthropic": (
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
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
    normalized = (provider or "claude").strip().lower()
    if normalized == "claude":
        return RunnerCapabilities(
            can_edit_files=True,
            can_run_shell=True,
            supports_native_skills=True,
            reliable_for_build=True,
            execution_model="cli",
            notes="Claude Code CLI: accès workspace + shell, skills natives via .claude/skills.",
        )
    if normalized == "codex":
        return RunnerCapabilities(
            can_edit_files=True,
            can_run_shell=True,
            supports_native_skills=False,
            reliable_for_build=True,
            execution_model="cli",
            notes="Codex CLI: accès workspace + shell; skills injectées via prompt/catalogue.",
        )
    if normalized in ("openai", "openrouter", "ollama", "anthropic"):
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
    """Build the agent backend for a provider name (AUTOSPEC_AGENT_PROVIDER)."""
    normalized = (provider or "claude").strip().lower()
    if normalized == "openai":
        return OpenAiRunner()
    if normalized == "openrouter":
        return OpenRouterRunner()
    if normalized == "ollama":
        return OllamaRunner()
    if normalized == "anthropic":
        return AnthropicRunner()
    if normalized == "codex":
        return CodexCliRunner()
    if normalized in ("", "claude"):
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
    if provider == "anthropic":
        return settings.anthropic_model
    if provider == "codex":
        return settings.codex_model or "(défaut Codex CLI)"
    return settings.claude_model or "(défaut CLI)"
