from pydantic import BaseModel
from uuid import UUID

class QueryAskingRequestModel(BaseModel):
    conversation_id: UUID
    user_query_content: str = ""
    role: str = "assistant"
    display_waiting_message: bool = True

class QueryNoConversationRequestModel(BaseModel):
    query: str
    type: str
    role: str = "assistant"
    user_name: str