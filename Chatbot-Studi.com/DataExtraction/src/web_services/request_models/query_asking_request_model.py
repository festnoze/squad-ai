from pydantic import BaseModel
from uuid import UUID

class QueryAskingRequestModel(BaseModel):
    conversation_id: UUID
    user_query_content: str = ""
    display_waiting_message: bool = True

class QueryNoConversationRequestModel(BaseModel):
    query: str
    type: str
    user_name: str