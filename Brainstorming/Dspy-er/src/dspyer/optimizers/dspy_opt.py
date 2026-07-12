from __future__ import annotations

import asyncio
import logging

from ..rendering import as_text
from .base import BaseOptimizer, OptimizationContext

logger = logging.getLogger(__name__)


class DspyOptimizer(BaseOptimizer):
    """Uses DSPy's BootstrapFewShot teleprompter to compile the prompt.

    The current prompt becomes the signature instructions; the compiled program's
    bootstrapped demos + (possibly rewritten) instructions are flattened back into a
    plain prompt text so the rest of the loop can evaluate it like any other candidate.
    DSPy is sync and mutates global settings, so the whole compile runs in a thread.
    """

    method_name = "dspy"

    async def apropose(self, ctx: OptimizationContext) -> list[str]:
        try:
            return await asyncio.to_thread(self._compile, ctx)
        except Exception as exc:  # noqa: BLE001 - DSPy failures must not kill the loop
            logger.warning("DSPy optimization failed: %s", exc)
            return []

    def _compile(self, ctx: OptimizationContext) -> list[str]:
        import dspy
        from dspy.teleprompt import BootstrapFewShot

        lm = dspy.LM(ctx.task_model, temperature=0.0, max_tokens=2000)

        signature = dspy.Signature(
            {"task_input": dspy.InputField(), "answer": dspy.OutputField()},
            instructions=ctx.current_prompt,
        )

        trainset = [
            dspy.Example(
                task_input=as_text(item.input), answer=as_text(item.expected_output)
            ).with_inputs("task_input")
            for item in ctx.train_items
        ]
        if len(trainset) < 2:
            return []

        def metric(example: "dspy.Example", prediction, trace=None) -> bool:
            expected = (example.answer or "").strip().lower()
            got = (getattr(prediction, "answer", "") or "").strip().lower()
            if not expected:
                return False
            return expected == got or expected in got

        with dspy.context(lm=lm):
            program = dspy.Predict(signature)
            teleprompter = BootstrapFewShot(
                metric=metric,
                max_bootstrapped_demos=min(4, len(trainset)),
                max_labeled_demos=min(4, len(trainset)),
                max_rounds=1,
            )
            compiled = teleprompter.compile(program, trainset=trainset)

        predictor = next(iter(compiled.predictors()), None)
        if predictor is None:
            return []

        instructions = predictor.signature.instructions or ctx.current_prompt
        demo_lines: list[str] = []
        for demo in getattr(predictor, "demos", [])[:4]:
            demo_input = getattr(demo, "task_input", None)
            demo_answer = getattr(demo, "answer", None)
            if demo_input and demo_answer:
                demo_lines += [f"Input: {demo_input}", f"Output: {demo_answer}", ""]

        candidate = instructions
        if demo_lines:
            candidate = instructions.rstrip() + "\n\n## Examples\n" + "\n".join(demo_lines)
        return [candidate]
