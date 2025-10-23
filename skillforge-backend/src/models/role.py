from uuid import UUID
from pydantic import BaseModel, ConfigDict


class Role(BaseModel):
    model_config = ConfigDict(
        frozen=True,  # Make it immutable
        json_encoders={UUID: str},
    )

    id: UUID
    name: str

    def to_dict(self) -> dict:
        """Convert Role model to dictionary for JSON serialization.

        Converts UUIDs to strings for JSON compatibility.

        Returns:
            dict: Dictionary representation with JSON-serializable values
        """
        return self.model_dump(mode="json")

    def to_json(self) -> str:
        """Convert Role model to JSON string.

        Returns:
            str: JSON string representation
        """
        return self.model_dump_json()
