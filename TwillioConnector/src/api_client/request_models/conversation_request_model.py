from uuid import UUID
from pydantic import BaseModel

class MessageRequestModel(BaseModel):
    role: str
    content: str
    duration_seconds: float = 0.0

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
            "duration_seconds": self.duration_seconds
        }

class ConversationRequestModel(BaseModel):
    user_id: UUID
    messages: list[MessageRequestModel]

    def to_dict(self):
        return {
            "user_id": str(self.user_id),
            "messages": [message.to_dict() for message in self.messages]
        }
