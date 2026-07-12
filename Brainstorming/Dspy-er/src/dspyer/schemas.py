from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class OptimizationMethod(str, enum.Enum):
    DSPY = "dspy"
    OPRO = "opro"
    COD = "cod"
    FEWSHOT = "fewshot"


class EvaluatorType(str, enum.Enum):
    EXACT_MATCH = "exact_match"
    CONTAINS = "contains"
    REGEX = "regex"
    JSON_VALID = "json_valid"
    SIMILARITY = "similarity"
    LLM_JUDGE = "llm_judge"
    LANGFUSE = "langfuse"


class EvaluatorSpec(BaseModel):
    """One evaluator to score model outputs against dataset expectations.

    - builtin types (exact_match, contains, regex, json_valid, similarity) need no config
      except `pattern` for regex.
    - llm_judge uses `criteria` (natural-language rubric) and an optional `judge_model`.
    - langfuse fetches the evaluator template by `name` from Langfuse and runs it
      locally as an LLM judge.
    """

    type: EvaluatorType
    name: str | None = None
    criteria: str | None = None
    pattern: str | None = None
    judge_model: str | None = None
    weight: float = Field(default=1.0, gt=0)


class OptimizationRequest(BaseModel):
    prompt_name: str = Field(description="Langfuse prompt name")
    prompt_label: str | None = Field(default=None, description="Langfuse prompt label (e.g. 'production')")
    prompt_version: int | None = Field(default=None, description="Explicit prompt version, overrides label")
    dataset_name: str = Field(description="Langfuse dataset name")
    evaluators: list[EvaluatorSpec] = Field(min_length=1)
    methods: list[OptimizationMethod] = Field(
        default=[OptimizationMethod.OPRO, OptimizationMethod.FEWSHOT],
        min_length=1,
        description="Optimization methods to run each round",
    )
    task_model: str | None = Field(
        default=None, description="Model executing the prompt (litellm id). Defaults to server setting."
    )
    candidate_models: list[str] = Field(
        default_factory=list,
        description="Extra models to benchmark the best prompt on (model-selection loop)",
    )
    rounds: int = Field(default=2, ge=1, le=10)
    candidates_per_method: int = Field(default=2, ge=1, le=8)
    train_split: float = Field(default=0.6, gt=0, lt=1)
    max_items: int | None = Field(default=None, ge=2, description="Cap dataset items (cost control)")
    temperature: float = Field(default=0.0, ge=0, le=2)
    push_best_to_langfuse: bool = Field(default=False)
    push_label: str = Field(default="optimized")


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CandidateResult(BaseModel):
    round: int
    method: str
    prompt: str
    train_score: float
    val_score: float | None = None
    accepted: bool = False


class ModelBenchmark(BaseModel):
    model: str
    score: float


class OptimizationResult(BaseModel):
    baseline_score: float
    best_score: float
    best_prompt: str
    best_model: str
    improvement: float
    model_benchmarks: list[ModelBenchmark] = Field(default_factory=list)
    history: list[CandidateResult] = Field(default_factory=list)
    per_evaluator_scores: dict[str, float] = Field(default_factory=dict)
    pushed_prompt_version: int | None = None


class JobInfo(BaseModel):
    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    request: OptimizationRequest
    progress: list[str] = Field(default_factory=list)
    result: OptimizationResult | None = None
    error: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
