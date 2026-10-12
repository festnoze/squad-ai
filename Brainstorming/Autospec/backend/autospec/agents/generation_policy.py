"""Opt-in campaign admission: Team Claude generates, external GPT reviews.

This is a trusted supervisor policy, not a prompt instruction or acceptance
proof. Generic installations keep their existing reviewer features unchanged.
"""
from pathlib import Path

from .personas import persona
from .runner import AgentError, AgentResult, AgentRunner


GENERATION_ROLES = frozenset({
    "pm", "sm", "po-structure", "po-spec", "po-gherkin", "dev", "dev-frontend",
    "analyst", "architect", "qa", "tech-writer", "classifier", "constitution",
    "cartographer",
})


class GenerationOnlyRunner:
    """Fail closed on unknown/reviewer roles or non-authorized model overrides."""
    def __init__(self, inner: AgentRunner, *, model: str = "sonnet"):
        self._inner = inner
        self._model = model

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def validate_call(self, system_prompt: str, model: str | None = None) -> None:
        if system_prompt not in {persona(role) for role in GENERATION_ROLES}:
            raise AgentError("GENERATION_ONLY: cette campagne réserve les revues aux sous-agents GPT externes.",
                code="GENERATION_ONLY", usage=AgentResult("", usage_reported=True))
        if model not in (None, self._model):
            raise AgentError("GENERATION_ONLY: modèle non autorisé pour la campagne.",
                code="GENERATION_ONLY", usage=AgentResult("", usage_reported=True))

    async def arun(self, prompt: str, system_prompt: str, cwd: Path | None = None,
                   session_id: str | None = None, model: str | None = None) -> AgentResult:
        self.validate_call(system_prompt, model)
        return await self._inner.arun(prompt, system_prompt, cwd=cwd,
            session_id=session_id, model=self._model)
