from pydantic import BaseModel
from typing import List

class MessageRequestModel(BaseModel):
    role: str
    content: str
    duration_seconds: float = 0.0

class ConversationRequestModel(BaseModel):
    messages: List[MessageRequestModel]
