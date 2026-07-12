from __future__ import annotations

import logging
import random
from typing import Callable

from .config import get_settings
from .evaluation import EvaluationEngine, abuild_evaluators
from .langfuse_service import DatasetItem, LangfuseService
from .llm import LLMClient
from .optimizers import OPTIMIZER_REGISTRY, OptimizationContext
from .schemas import (
    CandidateResult,
    ModelBenchmark,
    OptimizationRequest,
    OptimizationResult,
)

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]


def split_dataset(
    items: list[DatasetItem], train_split: float, max_items: int | None, seed: int = 42
) -> tuple[list[DatasetItem], list[DatasetItem]]:
    pool = list(items)
    random.Random(seed).shuffle(pool)
    if max_items:
        pool = pool[:max_items]
    if len(pool) < 2:
        raise ValueError(f"Dataset needs at least 2 usable items, got {len(pool)}")
    cut = max(1, min(len(pool) - 1, round(len(pool) * train_split)))
    return pool[:cut], pool[cut:]


async def arun_optimization(
    request: OptimizationRequest,
    langfuse: LangfuseService,
    llm: LLMClient | None = None,
    progress: ProgressFn = lambda msg: None,
) -> OptimizationResult:
    settings = get_settings()
    llm = llm or LLMClient()
    task_model = request.task_model or settings.default_task_model

    progress(f"Fetching prompt '{request.prompt_name}' and dataset '{request.dataset_name}' from Langfuse")
    prompt_data = await langfuse.aget_prompt(
        request.prompt_name, label=request.prompt_label, version=request.prompt_version
    )
    items = await langfuse.aget_dataset_items(request.dataset_name)
    train_items, val_items = split_dataset(items, request.train_split, request.max_items)
    progress(f"Dataset split: {len(train_items)} train / {len(val_items)} val items")

    evaluators = await abuild_evaluators(request.evaluators, llm, langfuse)
    engine = EvaluationEngine(llm, evaluators)

    # --- Baseline ---
    progress(f"Evaluating baseline prompt v{prompt_data.version} on {task_model}")
    baseline_val = await engine.aevaluate(prompt_data.text, task_model, val_items, request.temperature)
    baseline_train = await engine.aevaluate(prompt_data.text, task_model, train_items, request.temperature)
    progress(f"Baseline val score: {baseline_val.mean_score:.3f}")

    best_prompt = prompt_data.text
    best_score = baseline_val.mean_score
    best_report = baseline_val
    last_train_report = baseline_train
    history: list[CandidateResult] = []
    trajectory: list[tuple[str, float]] = [(prompt_data.text, baseline_val.mean_score)]

    optimizers = [OPTIMIZER_REGISTRY[m](llm) for m in request.methods]

    # --- Improvement rounds ---
    for round_idx in range(1, request.rounds + 1):
        for optimizer in optimizers:
            ctx = OptimizationContext(
                current_prompt=best_prompt,
                task_model=task_model,
                optimizer_model=settings.optimizer_model,
                train_items=train_items,
                last_report=last_train_report,
                history=trajectory,
                candidates_requested=request.candidates_per_method,
            )
            progress(f"Round {round_idx}: proposing candidates via {optimizer.method_name}")
            candidates = await optimizer.apropose(ctx)
            if not candidates:
                progress(f"Round {round_idx}: {optimizer.method_name} produced no candidates")
                continue

            # score candidates on train, promote the best to val
            scored: list[tuple[str, float]] = []
            for candidate in candidates:
                train_report = await engine.aevaluate(candidate, task_model, train_items, request.temperature)
                scored.append((candidate, train_report.mean_score))
            scored.sort(key=lambda pair: pair[1], reverse=True)

            top_prompt, top_train_score = scored[0]
            val_report = await engine.aevaluate(top_prompt, task_model, val_items, request.temperature)
            accepted = val_report.mean_score > best_score
            history.append(
                CandidateResult(
                    round=round_idx,
                    method=optimizer.method_name,
                    prompt=top_prompt,
                    train_score=top_train_score,
                    val_score=val_report.mean_score,
                    accepted=accepted,
                )
            )
            for candidate, train_score in scored[1:]:
                history.append(
                    CandidateResult(
                        round=round_idx,
                        method=optimizer.method_name,
                        prompt=candidate,
                        train_score=train_score,
                    )
                )
            trajectory.append((top_prompt, val_report.mean_score))
            progress(
                f"Round {round_idx} [{optimizer.method_name}] best candidate: "
                f"train={top_train_score:.3f} val={val_report.mean_score:.3f} "
                f"({'ACCEPTED' if accepted else 'rejected'} vs {best_score:.3f})"
            )
            if accepted:
                best_prompt = top_prompt
                best_score = val_report.mean_score
                best_report = val_report
                last_train_report = await engine.aevaluate(
                    best_prompt, task_model, train_items, request.temperature
                )

    # --- Model-selection loop: benchmark best prompt across candidate models ---
    benchmarks = [ModelBenchmark(model=task_model, score=best_score)]
    best_model = task_model
    for model in request.candidate_models:
        if model == task_model:
            continue
        progress(f"Benchmarking best prompt on {model}")
        try:
            report = await engine.aevaluate(best_prompt, model, val_items, request.temperature)
        except Exception as exc:  # noqa: BLE001
            progress(f"Model {model} failed benchmark: {exc}")
            continue
        benchmarks.append(ModelBenchmark(model=model, score=report.mean_score))
        if report.mean_score > best_score:
            best_score = report.mean_score
            best_model = model
            best_report = report
    benchmarks.sort(key=lambda b: b.score, reverse=True)

    # --- Optional push back to Langfuse ---
    pushed_version: int | None = None
    if request.push_best_to_langfuse and best_prompt != prompt_data.text:
        progress(f"Pushing best prompt to Langfuse with label '{request.push_label}'")
        pushed_version = await langfuse.acreate_prompt_version(
            name=request.prompt_name,
            prompt_text=best_prompt,
            labels=[request.push_label],
            config={**prompt_data.config, "optimized_by": "dspyer", "best_model": best_model},
            commit_message=(
                f"dspyer: {baseline_val.mean_score:.3f} -> {best_score:.3f} "
                f"({', '.join(m.value for m in request.methods)})"
            ),
        )
        progress(f"Created prompt version v{pushed_version}")

    await langfuse.ascore_run(
        name="dspyer_optimization_gain",
        value=best_score - baseline_val.mean_score,
        comment=f"prompt={request.prompt_name} dataset={request.dataset_name} model={best_model}",
    )
    langfuse.flush()

    return OptimizationResult(
        baseline_score=baseline_val.mean_score,
        best_score=best_score,
        best_prompt=best_prompt,
        best_model=best_model,
        improvement=best_score - baseline_val.mean_score,
        model_benchmarks=benchmarks,
        history=history,
        per_evaluator_scores=best_report.per_evaluator,
        pushed_prompt_version=pushed_version,
    )
