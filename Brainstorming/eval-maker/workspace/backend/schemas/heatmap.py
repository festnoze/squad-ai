"""Pydantic schemas for the heatmap response."""

from pydantic import BaseModel


class HeatmapRule(BaseModel):
    id: int
    rule_code: str
    text: str
    cluster_name: str | None = None


class HeatmapScenario(BaseModel):
    test_case_id: int
    scenario_type: str
    user_input_preview: str


class HeatmapCluster(BaseModel):
    id: int
    name: str
    rule_ids: list[int]


class HeatmapResponse(BaseModel):
    rules: list[HeatmapRule]
    scenarios: list[HeatmapScenario]
    matrix: list[list[int | None]]
    clusters: list[HeatmapCluster]


class LangfusePushResponse(BaseModel):
    dataset_name: str
    items_pushed: int
    eval_configs_created: int
