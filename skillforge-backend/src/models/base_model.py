from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class IdBaseModel(BaseModel):
    """Base model with uuid id.

    Attributes:
        id: Unique identifier (UUID)
    """

    model_config = ConfigDict(
        # frozen=True,  # Make it immutable
        json_encoders={UUID: str, datetime: lambda v: v.isoformat()},
    )

    id: UUID | None = None

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        return self.model_dump_json()


class IdStatefulBaseModel(IdBaseModel):
    """Base model with common fields for all domain models.

    Attributes:
        id: Unique identifier (UUID)
        created_at: Timestamp when the record was created
        updated_at: Timestamp when the record was last updated (optional)
        deleted_at: Timestamp when the record was soft-deleted (optional)
    """

    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        return self.model_dump_json()
