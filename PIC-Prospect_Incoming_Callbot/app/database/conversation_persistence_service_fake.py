from database.models.conversation import Conversation
from database.models.message import Message
from database.models.user import User
from database.conversation_repository import ConversationRepository
from api_client.conversation_persistence_interface import ConversationPersistenceInterface
from api_client.request_models.user_request_model import UserRequestModel
from api_client.request_models.conversation_request_model import ConversationRequestModel
from uuid import UUID
from typing import Dict, Any
from database.models.device_info import DeviceInfo
from database.user_repository import UserRepository

class QuotaOverloadException(Exception):
    pass

class ConversationPersistenceServiceFake(ConversationPersistenceInterface):
    def __init__(self):
        pass

    async def create_or_retrieve_user_async(self, user_request_model: UserRequestModel, timeout: int = 10) -> UUID:
        return UUID(ConversationPersistenceInterface.NoneUuid)
    
    async def create_new_conversation_async(self, conversation_request_model: ConversationRequestModel, timeout: int = 10) -> UUID:
        return UUID(ConversationPersistenceInterface.NoneUuid)

    async def get_user_last_conversation_async(self, user_id: UUID, timeout: int = 10) -> dict:
        return {"conversation_id": None, "user_id": None, "message_count": 0}
    
    async def add_message_to_user_last_conversation_or_create_one_async(self, user_id:UUID, new_message:str) -> Conversation:
        return {}
    
    async def add_external_ai_message_to_conversation_async(self, conversation_id: str, new_message: str, timeout: int = 10) -> dict:
        return {}
    