"""Pydantic schemas for JudgePrompt requests and responses."""

from pydantic import BaseModel


class JudgeOut(BaseModel):
    id: int
    cluster_id: int
    cluster_name: str
    rubric_rules_count: int

    model_config = {"from_attributes": True}


class JudgesResponse(BaseModel):
    judges: list[JudgeOut]
