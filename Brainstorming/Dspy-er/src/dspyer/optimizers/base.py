from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..evaluation import EvalReport
from ..langfuse_service import DatasetItem
from ..llm import LLMClient
from ..rendering import as_text


@dataclass
class OptimizationContext:
    """Everything an optimizer may look at when proposing new prompts."""

    current_prompt: str
    task_model: str
    optimizer_model: str
    train_items: list[DatasetItem]
    last_report: EvalReport | None = None
    history: list[tuple[str, float]] = field(default_factory=list)  # (prompt, val_score)
    candidates_requested: int = 2


class BaseOptimizer(ABC):
    method_name: str = "base"

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    @abstractmethod
    async def apropose(self, ctx: OptimizationContext) -> list[str]:
        """Return candidate prompt texts (may be empty on failure)."""


def format_failures(report: EvalReport | None, limit: int = 5) -> str:
    """Render the worst-scoring items as a feedback block for meta-prompts."""
    if report is None or not report.item_results:
        return "(no evaluation feedback available yet)"
    worst = sorted(report.item_results, key=lambda r: r.score)[:limit]
    blocks = []
    for r in worst:
        blocks.append(
            f"- score={r.score:.2f}\n"
            f"  input: {as_text(r.item.input)[:600]}\n"
            f"  expected: {as_text(r.item.expected_output)[:600]}\n"
            f"  got: {r.output[:600]}"
        )
    return "\n".join(blocks)


def parse_prompt_blocks(raw: str) -> list[str]:
    """Extract prompts wrapped in <PROMPT>...</PROMPT> tags from an LLM response."""
    import re

    blocks = re.findall(r"<PROMPT>(.*?)</PROMPT>", raw, re.DOTALL | re.IGNORECASE)
    cleaned = [b.strip() for b in blocks if b.strip()]
    if not cleaned and raw.strip():
        # fall back: treat whole response as one candidate if it looks like a prompt
        text = raw.strip()
        if len(text) > 40 and not text.lower().startswith(("i can", "i'm sorry", "sure", "here")):
            cleaned = [text]
    return cleaned
