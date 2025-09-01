from uuid import UUID

from pydantic import BaseModel


class MessageRequestModel(BaseModel):
    role: str
    content: str
    elapsed_seconds: float = 0.0

    def to_dict(self):
        return {"role": self.role, "content": self.content, "elapsed_seconds": self.elapsed_seconds}


class ConversationRequestModel(BaseModel):
    user_id: UUID | None = None
    messages: list[MessageRequestModel] = []
    conversation_id: UUID | None = None

    def to_dict(self):
        return {
            "user_id": str(self.user_id),
            "messages": [message.to_dict() for message in self.messages],
            "conversation_id": str(self.conversation_id),
        }
