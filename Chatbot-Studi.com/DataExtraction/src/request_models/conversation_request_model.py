from pydantic import BaseModel
from typing import List

class MessageRequestModel(BaseModel):
    source: str
    content: str
    duration_seconds: int = 0
    is_saved_message: bool = True
    is_end_message: bool = False

class ConversationRequestModel(BaseModel):
    messages: List[MessageRequestModel]
