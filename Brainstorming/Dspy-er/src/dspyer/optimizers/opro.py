from __future__ import annotations

import logging

from .base import BaseOptimizer, OptimizationContext, format_failures, parse_prompt_blocks

logger = logging.getLogger(__name__)

OPRO_META_PROMPT = """You are an expert prompt engineer performing OPRO-style optimization.
Your job: write improved versions of a prompt so a task model scores higher on an eval set.

## Current prompt (score trajectory below)
<CURRENT>
{current_prompt}
</CURRENT>

## Previous attempts and their validation scores (higher is better, max 1.0)
{trajectory}

## Worst-scoring examples with the current prompt
{failures}

## Instructions
- Diagnose WHY the current prompt fails on those examples.
- Write {n} DIFFERENT improved prompts. Vary the strategy across candidates
  (e.g. stricter output format, added reasoning steps, explicit constraints, role framing).
- Keep every {{{{variable}}}} placeholder from the current prompt intact.
- Do not overfit to the shown examples; generalize the fix.

Return each candidate wrapped in its own <PROMPT>...</PROMPT> tags. No other commentary."""


class OproOptimizer(BaseOptimizer):
    method_name = "opro"

    async def apropose(self, ctx: OptimizationContext) -> list[str]:
        trajectory = "\n".join(
            f"- score={score:.3f}: {prompt[:150].replace(chr(10), ' ')}..."
            for prompt, score in ctx.history[-8:]
        ) or "(first round)"
        meta = OPRO_META_PROMPT.format(
            current_prompt=ctx.current_prompt,
            trajectory=trajectory,
            failures=format_failures(ctx.last_report),
            n=ctx.candidates_requested,
        )
        try:
            raw = await self._llm.acomplete(
                ctx.optimizer_model, [{"role": "user", "content": meta}], temperature=0.9
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OPRO proposal failed: %s", exc)
            return []
        return parse_prompt_blocks(raw)[: ctx.candidates_requested]
