from uuid import UUID
from pydantic import BaseModel

class CreateNewConversationRequestModel(BaseModel):
    user_id: UUID
    messages: list[str] = []

    def to_json(self) -> dict:
        return {"user_id": str(self.user_id), "messages": []}

