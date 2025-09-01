from uuid import UUID

from pydantic import BaseModel


class QueryAskingRequestModel(BaseModel):
    conversation_id: UUID
    user_query_content: str = ""
    role: str = "assistant"
    display_waiting_message: bool = True

    def to_dict(self):
        return {
            "conversation_id": str(self.conversation_id),
            "user_query_content": self.user_query_content,
            "role": self.role,
            "display_waiting_message": self.display_waiting_message,
        }


class QueryNoConversationRequestModel(BaseModel):
    query: str
    type: str
    role: str = "assistant"
    user_name: str

    def to_dict(self):
        return {"query": self.query, "type": self.type, "role": self.role, "user_name": self.user_name}
