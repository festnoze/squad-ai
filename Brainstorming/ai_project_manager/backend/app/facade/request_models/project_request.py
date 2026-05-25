"""Request models for `/api/projects` endpoints.

These Pydantic models drive FastAPI's automatic validation: an empty `name` or
one longer than 255 characters is rejected with HTTP 422 before our router
code runs.
"""

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    """Payload required to create a new project."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class UpdateProjectRequest(BaseModel):
    """Partial update payload — every field is optional.

    Because fields default to `None`, use `.model_dump(exclude_unset=True)` at
    the call site to avoid overwriting stored values with `None`.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
