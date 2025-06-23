from pydantic import BaseModel
from uuid import UUID

class QueryAskingRequestModel(BaseModel):
    conversation_id: UUID
    user_query_content: str = ""
    display_waiting_message: bool = True
    
    def to_dict(self):
        return {
            "conversation_id": str(self.conversation_id),
            "user_query_content": self.user_query_content,
            "display_waiting_message": self.display_waiting_message
        }

class QueryNoConversationRequestModel(BaseModel):
    query: str
    type: str
    user_name: str
    
    def to_dict(self):
        return {
            "query": self.query,
            "type": self.type,
            "user_name": self.user_name
        }