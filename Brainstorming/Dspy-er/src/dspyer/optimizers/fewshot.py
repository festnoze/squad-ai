from __future__ import annotations

import logging
import random

from ..rendering import as_text
from .base import BaseOptimizer, OptimizationContext

logger = logging.getLogger(__name__)


class FewShotOptimizer(BaseOptimizer):
    """Appends worked examples from the training set to the prompt.

    Candidate 1 uses items the current prompt already solves well (bootstrap style,
    reinforces the winning pattern); candidate 2 uses the hardest items (teaches the
    failure modes). Expected outputs come from the dataset, so demos are always correct.
    """

    method_name = "fewshot"
    shots = 3

    def _format_block(self, items) -> str:
        lines = ["", "## Examples"]
        for item in items:
            lines.append(f"Input: {as_text(item.input)[:800]}")
            lines.append(f"Output: {as_text(item.expected_output)[:800]}")
            lines.append("")
        return "\n".join(lines)

    async def apropose(self, ctx: OptimizationContext) -> list[str]:
        if not ctx.train_items:
            return []
        base = ctx.current_prompt.rstrip()
        candidates: list[str] = []

        if ctx.last_report and ctx.last_report.item_results:
            ranked = sorted(ctx.last_report.item_results, key=lambda r: r.score, reverse=True)
            easy = [r.item for r in ranked[: self.shots]]
            hard = [r.item for r in ranked[-self.shots :]]
        else:
            pool = list(ctx.train_items)
            random.shuffle(pool)
            easy, hard = pool[: self.shots], pool[self.shots : 2 * self.shots]

        if easy:
            candidates.append(base + self._format_block(easy))
        if hard and [i.id for i in hard] != [i.id for i in easy]:
            candidates.append(base + self._format_block(hard))
        return candidates[: max(ctx.candidates_requested, 1)]
