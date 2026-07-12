from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .config import get_settings
from .langfuse_service import DatasetItem, LangfuseService
from .llm import LLMClient
from .rendering import as_text, render_messages
from .schemas import EvaluatorSpec, EvaluatorType

logger = logging.getLogger(__name__)

JUDGE_TEMPLATE = """You are a strict evaluator. Score the OUTPUT of an AI system.

## Rubric
{criteria}

## Task input
{input}

## Expected output (reference; may be empty)
{expected}

## Actual output
{output}

Respond with ONLY a JSON object: {{"score": <float between 0.0 and 1.0>, "reason": "<one sentence>"}}"""


class Evaluator(ABC):
    def __init__(self, spec: EvaluatorSpec) -> None:
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name or self.spec.type.value

    @abstractmethod
    async def ascore(self, item: DatasetItem, output: str) -> float:
        """Return a score in [0, 1]."""


class ExactMatchEvaluator(Evaluator):
    async def ascore(self, item: DatasetItem, output: str) -> float:
        return 1.0 if output.strip() == as_text(item.expected_output).strip() else 0.0


class ContainsEvaluator(Evaluator):
    async def ascore(self, item: DatasetItem, output: str) -> float:
        expected = as_text(item.expected_output).strip()
        return 1.0 if expected and expected.lower() in output.lower() else 0.0


class RegexEvaluator(Evaluator):
    async def ascore(self, item: DatasetItem, output: str) -> float:
        pattern = self.spec.pattern or as_text(item.expected_output)
        try:
            return 1.0 if re.search(pattern, output) else 0.0
        except re.error:
            logger.warning("Invalid regex pattern: %s", pattern)
            return 0.0


class JsonValidEvaluator(Evaluator):
    async def ascore(self, item: DatasetItem, output: str) -> float:
        text = output.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
        try:
            json.loads(text)
            return 1.0
        except json.JSONDecodeError:
            return 0.0


class SimilarityEvaluator(Evaluator):
    async def ascore(self, item: DatasetItem, output: str) -> float:
        expected = as_text(item.expected_output)
        if not expected:
            return 0.0
        return difflib.SequenceMatcher(None, output.strip().lower(), expected.strip().lower()).ratio()


class LLMJudgeEvaluator(Evaluator):
    def __init__(self, spec: EvaluatorSpec, llm: LLMClient, criteria: str | None = None) -> None:
        super().__init__(spec)
        self._llm = llm
        self._criteria = criteria or spec.criteria or "Overall correctness and helpfulness versus the expected output."
        self._model = spec.judge_model or get_settings().judge_model

    async def ascore(self, item: DatasetItem, output: str) -> float:
        prompt = JUDGE_TEMPLATE.format(
            criteria=self._criteria,
            input=as_text(item.input)[:4000],
            expected=as_text(item.expected_output)[:4000],
            output=output[:4000],
        )
        try:
            raw = await self._llm.acomplete(self._model, [{"role": "user", "content": prompt}])
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                return 0.0
            score = float(json.loads(match.group(0)).get("score", 0.0))
            return max(0.0, min(1.0, score))
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM judge failed: %s", exc)
            return 0.0


async def abuild_evaluators(
    specs: list[EvaluatorSpec], llm: LLMClient, langfuse: LangfuseService
) -> list[Evaluator]:
    evaluators: list[Evaluator] = []
    for spec in specs:
        match spec.type:
            case EvaluatorType.EXACT_MATCH:
                evaluators.append(ExactMatchEvaluator(spec))
            case EvaluatorType.CONTAINS:
                evaluators.append(ContainsEvaluator(spec))
            case EvaluatorType.REGEX:
                evaluators.append(RegexEvaluator(spec))
            case EvaluatorType.JSON_VALID:
                evaluators.append(JsonValidEvaluator(spec))
            case EvaluatorType.SIMILARITY:
                evaluators.append(SimilarityEvaluator(spec))
            case EvaluatorType.LLM_JUDGE:
                evaluators.append(LLMJudgeEvaluator(spec, llm))
            case EvaluatorType.LANGFUSE:
                if not spec.name:
                    raise ValueError("langfuse evaluator requires 'name'")
                criteria = await langfuse.aget_evaluator_criteria(spec.name)
                evaluators.append(LLMJudgeEvaluator(spec, llm, criteria=criteria))
    return evaluators


@dataclass
class ItemResult:
    item: DatasetItem
    output: str
    score: float
    per_evaluator: dict[str, float] = field(default_factory=dict)


@dataclass
class EvalReport:
    mean_score: float
    per_evaluator: dict[str, float]
    item_results: list[ItemResult]


class EvaluationEngine:
    """Runs a prompt against dataset items on a model and scores the outputs."""

    def __init__(self, llm: LLMClient, evaluators: list[Evaluator]) -> None:
        self._llm = llm
        self._evaluators = evaluators

    async def _arun_item(
        self, prompt_text: str, model: str, item: DatasetItem, temperature: float
    ) -> ItemResult:
        messages = render_messages(prompt_text, item.input)
        try:
            output = await self._llm.acomplete(model, messages, temperature=temperature)
        except Exception as exc:  # noqa: BLE001 - a dead item scores 0, run continues
            logger.warning("Task model call failed for item %s: %s", item.id, exc)
            return ItemResult(item=item, output=f"<error: {exc}>", score=0.0)

        per_evaluator: dict[str, float] = {}
        total_weight = 0.0
        weighted = 0.0
        for evaluator in self._evaluators:
            score = await evaluator.ascore(item, output)
            per_evaluator[evaluator.name] = score
            weighted += score * evaluator.spec.weight
            total_weight += evaluator.spec.weight
        final = weighted / total_weight if total_weight else 0.0
        return ItemResult(item=item, output=output, score=final, per_evaluator=per_evaluator)

    async def aevaluate(
        self,
        prompt_text: str,
        model: str,
        items: list[DatasetItem],
        temperature: float = 0.0,
    ) -> EvalReport:
        results = await asyncio.gather(
            *(self._arun_item(prompt_text, model, item, temperature) for item in items)
        )
        item_results = list(results)
        mean = sum(r.score for r in item_results) / len(item_results) if item_results else 0.0
        per_evaluator: dict[str, float] = {}
        for evaluator in self._evaluators:
            scores = [r.per_evaluator.get(evaluator.name, 0.0) for r in item_results]
            per_evaluator[evaluator.name] = sum(scores) / len(scores) if scores else 0.0
        return EvalReport(mean_score=mean, per_evaluator=per_evaluator, item_results=item_results)
