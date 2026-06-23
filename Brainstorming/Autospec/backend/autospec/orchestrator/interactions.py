"""Per-item capture of LLM round-trips for live introspection.

Every agent call funnels through ``Pipeline._UsageTracker.arun`` (the single
chokepoint that also accumulates token/cost usage). Each call is recorded here as
an :class:`AgentInteraction`, keyed by the work item it belongs to (a user story
or task id during BUILD, or ``"phase:<phase>"`` for planning-phase calls). The
operator can then open an item and read the exact prompts/answers the factory
exchanged with the model.

Storage is twofold and deliberately outside ``ProjectState`` (whose JSON is
re-serialized and broadcast on every ``_sync`` — prompts/answers are far too
large for that): a bounded in-memory ring per item for the live fast path, and a
best-effort JSONL sidecar so history survives a backend reload and can be served
even for a dormant (not-in-memory) project.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Callable

from ..models import AgentInteraction

# Cap how much of a single prompt/response we keep. Dev prompts can embed whole
# files; storing them verbatim would bloat the sidecar without adding value.
MAX_TEXT_CHARS = 16_000

# Recent calls kept in memory per item. A single item rarely exceeds a handful of
# qa/dev/critic/judge rounds × a few retries; this is generous.
PER_ITEM_RING = 40


def _truncate(text: str) -> tuple[str, bool]:
    text = text or ""
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS] + "\n…[tronqué]", True


class InteractionStore:
    """In-memory ring of recent :class:`AgentInteraction` per work item, with an
    optional persist hook (wired by the pipeline to the JSONL sidecar)."""

    def __init__(
        self,
        per_item: int = PER_ITEM_RING,
        persist: Callable[[AgentInteraction], None] | None = None,
    ) -> None:
        self._per_item = per_item
        self._by_item: dict[str, deque[AgentInteraction]] = defaultdict(
            lambda: deque(maxlen=per_item)
        )
        self._persist = persist

    def record(
        self,
        *,
        item_id: str,
        phase: str,
        persona: str,
        prompt: str,
        response: str,
        ok: bool = True,
        error: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        duration_ms: int = 0,
    ) -> AgentInteraction:
        prompt_text, prompt_trunc = _truncate(prompt)
        resp_text, resp_trunc = _truncate(response)
        interaction = AgentInteraction(
            item_id=item_id,
            phase=phase,
            persona=persona,
            prompt=prompt_text,
            response=resp_text,
            ok=ok,
            error=error,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            prompt_truncated=prompt_trunc,
            response_truncated=resp_trunc,
        )
        self._by_item[item_id].append(interaction)
        if self._persist is not None:
            self._persist(interaction)
        return interaction

    def add_existing(self, interaction: AgentInteraction) -> None:
        """Insert an already-built interaction (e.g. loaded from the sidecar on
        startup) without re-persisting it."""
        self._by_item[interaction.item_id].append(interaction)

    def for_item(self, item_id: str, limit: int | None = None) -> list[AgentInteraction]:
        """The recent interactions for an item, oldest→newest. ``limit`` keeps the
        newest N."""
        items = list(self._by_item.get(item_id, ()))
        if limit is not None and limit >= 0:
            items = items[-limit:]
        return items

    def has_item(self, item_id: str) -> bool:
        return bool(self._by_item.get(item_id))
