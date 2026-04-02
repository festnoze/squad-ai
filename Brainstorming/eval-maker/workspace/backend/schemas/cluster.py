"""Pydantic schemas for Cluster requests and responses."""

from pydantic import BaseModel


class ClusterOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    rule_count: int = 0

    model_config = {"from_attributes": True}


class ClusterResponse(BaseModel):
    clusters: list[ClusterOut]
