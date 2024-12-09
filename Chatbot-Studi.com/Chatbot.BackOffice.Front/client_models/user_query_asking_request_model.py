from pydantic import BaseModel
from typing import Union
from uuid import UUID

class UserQueryAskingRequestModel(BaseModel):
    conversation_id: UUID
    user_query_content: str = ""
    display_waiting_message: bool = False

    def to_json(self) -> dict[str, Union[str, UUID]]:
        return {"conversation_id": str(self.conversation_id), "user_query_content": self.user_query_content, "display_waiting_message": self.display_waiting_message}