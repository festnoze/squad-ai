from uuid import UUID
from pydantic import BaseModel

class MessageRequestModel(BaseModel):
    role: str
    content: str
    duration_seconds: float = 0.0

class ConversationRequestModel(BaseModel):
    user_id: UUID
    messages: list[MessageRequestModel]
