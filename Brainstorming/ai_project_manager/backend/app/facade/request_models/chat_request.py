"""Request models for `/api/projects/{project_id}/messages` endpoints."""

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    """Payload required to post a new user message in the scoping chat."""

    content: str = Field(min_length=1, max_length=10000)
