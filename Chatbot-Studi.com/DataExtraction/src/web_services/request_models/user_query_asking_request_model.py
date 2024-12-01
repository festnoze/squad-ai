from pydantic import BaseModel
from uuid import UUID

class UserQueryAskingRequestModel(BaseModel):
    conversation_id: UUID
    user_query_content: str = ""