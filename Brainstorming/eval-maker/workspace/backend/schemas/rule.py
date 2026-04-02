"""Pydantic schemas for Rule requests and responses."""

from pydantic import BaseModel


class ClusterBrief(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class RuleOut(BaseModel):
    id: int
    rule_code: str
    text: str
    source_section: str | None = None
    is_explicit: bool = True
    cluster: ClusterBrief | None = None

    model_config = {"from_attributes": True}


class ExtractRequest(BaseModel):
    prompt_text: str


class ExtractResponse(BaseModel):
    rules_count: int
    rules: list[RuleOut]


class RulesListResponse(BaseModel):
    rules: list[RuleOut]
