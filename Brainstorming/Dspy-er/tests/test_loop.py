from __future__ import annotations

import pytest

from dspyer.langfuse_service import DatasetItem
from dspyer.loop import arun_optimization, split_dataset
from dspyer.schemas import EvaluatorSpec, EvaluatorType, OptimizationMethod, OptimizationRequest


def make_request(**overrides) -> OptimizationRequest:
    defaults = dict(
        prompt_name="capitals",
        dataset_name="capitals-ds",
        evaluators=[EvaluatorSpec(type=EvaluatorType.EXACT_MATCH)],
        methods=[OptimizationMethod.OPRO],
        task_model="test-model",
        rounds=1,
        candidates_per_method=1,
        train_split=0.6,
    )
    defaults.update(overrides)
    return OptimizationRequest(**defaults)


def test_split_dataset_deterministic():
    items = [DatasetItem(id=str(i), input=i, expected_output=i) for i in range(10)]
    train1, val1 = split_dataset(items, 0.6, None)
    train2, val2 = split_dataset(items, 0.6, None)
    assert [i.id for i in train1] == [i.id for i in train2]
    assert len(train1) == 6 and len(val1) == 4
    assert not {i.id for i in train1} & {i.id for i in val1}


def test_split_dataset_too_small():
    with pytest.raises(ValueError):
        split_dataset([DatasetItem(id="1", input=1, expected_output=1)], 0.6, None)


async def test_optimization_improves_score(fake_llm, fake_langfuse):
    result = await arun_optimization(make_request(), fake_langfuse, llm=fake_llm)
    # baseline prompt yields verbose answers -> exact_match 0; OPRO proposes 'BE PRECISE' prompt -> 1.0
    assert result.baseline_score == 0.0
    assert result.best_score == 1.0
    assert "BE PRECISE" in result.best_prompt
    assert result.improvement == 1.0
    assert any(c.accepted for c in result.history)


async def test_push_best_to_langfuse(fake_llm, fake_langfuse):
    request = make_request(push_best_to_langfuse=True, push_label="optimized")
    result = await arun_optimization(request, fake_langfuse, llm=fake_llm)
    assert result.pushed_prompt_version == 4
    assert fake_langfuse.pushed[0]["labels"] == ["optimized"]


async def test_model_benchmark_loop(fake_llm, fake_langfuse):
    request = make_request(candidate_models=["other-model"])
    result = await arun_optimization(request, fake_langfuse, llm=fake_llm)
    assert {b.model for b in result.model_benchmarks} == {"test-model", "other-model"}


async def test_fewshot_and_cod_methods_run(fake_llm, fake_langfuse):
    request = make_request(methods=[OptimizationMethod.FEWSHOT, OptimizationMethod.COD])
    result = await arun_optimization(request, fake_langfuse, llm=fake_llm)
    methods_seen = {c.method for c in result.history}
    assert "fewshot" in methods_seen
    assert "cod" in methods_seen
