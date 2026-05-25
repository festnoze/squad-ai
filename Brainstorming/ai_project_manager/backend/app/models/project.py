"""Project domain model (Pydantic)."""

from app.models.base_model import IdStatefulBaseModel


class Project(IdStatefulBaseModel):
    """A user-owned project containing items and chat history.

    Attributes:
        name: Human-readable project name (required).
        description: Optional free-text description.
    """

    name: str
    description: str | None = None
