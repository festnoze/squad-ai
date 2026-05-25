"""Base Pydantic domain models.

The domain layer is pure Pydantic — no SQLAlchemy in sight. These base models
provide common `id` and audit fields and configure `from_attributes=True` so
instances can be built directly from SQLAlchemy entities via
`Model.model_validate(entity)`.
"""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IdBaseModel(BaseModel):
    """Base model that only carries an `id`."""

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()},
    )

    id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.model_dump(mode="json"))

    def to_json(self) -> str:
        return cast(str, self.model_dump_json())


class IdStatefulBaseModel(IdBaseModel):
    """Base model for any entity tracked with audit timestamps."""

    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
