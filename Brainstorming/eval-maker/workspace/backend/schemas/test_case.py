"""Pydantic schemas for TestCase requests and responses."""

from pydantic import BaseModel


class DatasetRequest(BaseModel):
    scenario_types: list[str] = ["baseline", "edge", "adversarial"]
    cases_per_rule_per_type: int = 2
    concurrency: int = 10


class DatasetResponse(BaseModel):
    test_cases_count: int
    by_type: dict[str, int]
