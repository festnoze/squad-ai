"""Response model for `/api/projects` endpoints.

Kept intentionally minimal: it mirrors the persisted `Project` domain model but
exposes only the fields the frontend needs. We deliberately hide `deleted_at`
from public payloads.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectResponse(BaseModel):
    """Serialized view of a `Project` returned by the HTTP layer."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()},
    )

    id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
