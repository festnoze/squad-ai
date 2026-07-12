from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from dspyer.langfuse_service import DatasetItem, LangfuseService, PromptData


class FakeLLM:
    """Deterministic stand-in for LLMClient.

    - task calls (system prompt containing 'CAPITALS'): answers correctly only when the
      prompt contains the magic token 'BE PRECISE', so optimization can improve scores.
    - optimizer meta-prompt calls: returns an improved prompt containing the token.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def acomplete(self, model, messages, temperature=0.0, max_tokens=None):
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in messages if m["role"] == "user"), "")
        self.calls.append((model, system or user))

        if "<CURRENT>" in user or "<PROMPT>" in user or "prompt engineer" in user.lower() or "densify" in user.lower():
            return "<PROMPT>Answer with the capital city only. BE PRECISE.</PROMPT>"
        if "strict evaluator" in user.lower():
            return '{"score": 0.8, "reason": "ok"}'

        # task execution: correct answers only with the improved prompt
        answers = {"France": "Paris", "Spain": "Madrid", "Italy": "Rome", "Japan": "Tokyo", "Peru": "Lima"}
        combined = f"{system} {user}".lower()
        for country, capital in answers.items():
            if country.lower() in combined:
                if "BE PRECISE" in system:
                    return capital
                return f"The capital of {country} is {capital}, a lovely city."
        return "I don't know."


class FakeLangfuseService(LangfuseService):
    def __init__(self) -> None:  # do not call super: no client
        self.pushed: list[dict] = []
        self.scores: list[dict] = []

    async def aget_prompt(self, name, label=None, version=None) -> PromptData:
        return PromptData(name=name, version=3, text="Answer the question about {{country}}.", is_chat=False)

    async def aget_dataset_items(self, dataset_name) -> list[DatasetItem]:
        data = [("France", "Paris"), ("Spain", "Madrid"), ("Italy", "Rome"), ("Japan", "Tokyo"), ("Peru", "Lima")]
        return [
            DatasetItem(id=f"item-{i}", input={"country": c}, expected_output=cap)
            for i, (c, cap) in enumerate(data)
        ]

    async def acreate_prompt_version(self, name, prompt_text, labels, config=None, commit_message=None) -> int:
        self.pushed.append({"name": name, "prompt": prompt_text, "labels": labels})
        return 4

    async def aget_evaluator_criteria(self, evaluator_name) -> str:
        return f"Judge output quality for '{evaluator_name}'."

    async def ascore_run(self, name, value, comment=None) -> None:
        self.scores.append({"name": name, "value": value})

    def flush(self) -> None:
        pass


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_langfuse() -> FakeLangfuseService:
    return FakeLangfuseService()
