from __future__ import annotations

import logging

from .base import BaseOptimizer, OptimizationContext, format_failures, parse_prompt_blocks

logger = logging.getLogger(__name__)

COD_STEP_PROMPT = """You are refining a prompt using Chain-of-Density: each pass makes the prompt
denser and more precise WITHOUT making it longer than ~1.5x the original.

## Prompt to densify (pass {step}/{steps})
<CURRENT>
{current_prompt}
</CURRENT>

## Observed failures on the eval set
{failures}

## This pass
1. Identify 2-3 missing specifics: implicit assumptions the task model gets wrong,
   unstated output-format rules, unhandled edge cases seen in the failures.
2. Rewrite the prompt, fusing those specifics in. Remove filler words to make room.
   Every sentence must carry an actionable constraint.
3. Keep every {{{{variable}}}} placeholder intact.

Return ONLY the rewritten prompt wrapped in <PROMPT>...</PROMPT> tags."""


class ChainOfDensityOptimizer(BaseOptimizer):
    """Iteratively densifies the prompt: several sequential refinement passes,
    each folding missing specifics into a same-length rewrite."""

    method_name = "cod"
    steps = 3

    async def apropose(self, ctx: OptimizationContext) -> list[str]:
        candidates: list[str] = []
        current = ctx.current_prompt
        failures = format_failures(ctx.last_report)
        for step in range(1, self.steps + 1):
            meta = COD_STEP_PROMPT.format(
                step=step, steps=self.steps, current_prompt=current, failures=failures
            )
            try:
                raw = await self._llm.acomplete(
                    ctx.optimizer_model, [{"role": "user", "content": meta}], temperature=0.4
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("CoD pass %d failed: %s", step, exc)
                break
            blocks = parse_prompt_blocks(raw)
            if not blocks:
                break
            current = blocks[0]
            candidates.append(current)
        # densest passes first; cap to requested count
        return list(reversed(candidates))[: ctx.candidates_requested]
