"""Response models for the `/api/projects/{id}/runs` endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectRunStepResponse(BaseModel):
    """Serialized view of a `ProjectRunStep`."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()},
    )

    id: UUID
    run_id: UUID
    item_id: UUID | None = None
    role: str  # "orchestrator" | "dev" | "qa"
    status: str  # "running" | "succeeded" | "failed" | "rejected"
    iteration: int
    summary: str
    detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ProjectRunResponse(BaseModel):
    """Serialized view of a `ProjectRun`, with counters."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()},
    )

    id: UUID
    project_id: UUID
    status: str  # "pending" | "running" | "succeeded" | "failed"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    total_tasks: int
    done_tasks: int
    blocked_tasks: int
    created_at: datetime
    updated_at: datetime | None = None


class ProjectRunDetailResponse(BaseModel):
    """Envelope returned by GET /projects/{id}/runs/current."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()},
    )

    run: ProjectRunResponse
    steps: list[ProjectRunStepResponse]
