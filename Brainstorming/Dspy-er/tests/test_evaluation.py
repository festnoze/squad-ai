from __future__ import annotations

import pytest

from dspyer.evaluation import (
    ContainsEvaluator,
    EvaluationEngine,
    ExactMatchEvaluator,
    JsonValidEvaluator,
    RegexEvaluator,
    SimilarityEvaluator,
)
from dspyer.langfuse_service import DatasetItem
from dspyer.rendering import render_messages
from dspyer.schemas import EvaluatorSpec, EvaluatorType

ITEM = DatasetItem(id="1", input={"country": "France"}, expected_output="Paris")


def spec(t: EvaluatorType, **kwargs) -> EvaluatorSpec:
    return EvaluatorSpec(type=t, **kwargs)


async def test_exact_match():
    ev = ExactMatchEvaluator(spec(EvaluatorType.EXACT_MATCH))
    assert await ev.ascore(ITEM, "Paris") == 1.0
    assert await ev.ascore(ITEM, " Paris \n") == 1.0
    assert await ev.ascore(ITEM, "paris is nice") == 0.0


async def test_contains():
    ev = ContainsEvaluator(spec(EvaluatorType.CONTAINS))
    assert await ev.ascore(ITEM, "The capital is PARIS.") == 1.0
    assert await ev.ascore(ITEM, "Lyon") == 0.0


async def test_regex():
    ev = RegexEvaluator(spec(EvaluatorType.REGEX, pattern=r"^Par\w+$"))
    assert await ev.ascore(ITEM, "Paris") == 1.0
    assert await ev.ascore(ITEM, "in Paris") == 0.0


async def test_json_valid():
    ev = JsonValidEvaluator(spec(EvaluatorType.JSON_VALID))
    assert await ev.ascore(ITEM, '{"a": 1}') == 1.0
    assert await ev.ascore(ITEM, '```json\n{"a": 1}\n```') == 1.0
    assert await ev.ascore(ITEM, "not json") == 0.0


async def test_similarity_bounds():
    ev = SimilarityEvaluator(spec(EvaluatorType.SIMILARITY))
    assert await ev.ascore(ITEM, "Paris") == pytest.approx(1.0)
    assert 0.0 <= await ev.ascore(ITEM, "Parys") < 1.0


def test_render_messages_dict_substitution():
    messages = render_messages("Tell me about {{country}}.", {"country": "France"})
    assert messages[0] == {"role": "system", "content": "Tell me about France."}


def test_render_messages_leftover_goes_to_user():
    messages = render_messages("Static prompt.", {"question": "Why?"})
    assert "Why?" in messages[1]["content"]


def test_render_messages_scalar_input():
    messages = render_messages("System rules.", "What is 2+2?")
    assert messages == [
        {"role": "system", "content": "System rules."},
        {"role": "user", "content": "What is 2+2?"},
    ]


async def test_engine_weighted_scores(fake_llm):
    engine = EvaluationEngine(
        fake_llm,
        [
            ExactMatchEvaluator(spec(EvaluatorType.EXACT_MATCH, weight=3.0)),
            ContainsEvaluator(spec(EvaluatorType.CONTAINS, weight=1.0)),
        ],
    )
    items = [DatasetItem(id="1", input={"country": "France"}, expected_output="Paris")]
    # bad prompt: verbose answer -> exact=0, contains=1 -> weighted (0*3+1*1)/4
    report = await engine.aevaluate("Answer about {{country}}.", "test-model", items)
    assert report.mean_score == pytest.approx(0.25)
    # good prompt with magic token -> exact answer
    report = await engine.aevaluate("Answer about {{country}}. BE PRECISE", "test-model", items)
    assert report.mean_score == pytest.approx(1.0)
