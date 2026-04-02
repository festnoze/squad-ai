"""Pydantic schemas for EvalResult requests and responses."""

from pydantic import BaseModel


class RunEvalsRequest(BaseModel):
    test_case_ids: list[int] | None = None
    concurrency: int = 5


class RunEvalsResponse(BaseModel):
    results_count: int
    average_score: float
    completed: bool
