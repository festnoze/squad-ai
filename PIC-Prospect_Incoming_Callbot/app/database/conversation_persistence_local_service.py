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

class ConversationPersistenceLocalService(ConversationPersistenceInterface):
    def __init__(self) -> None:
        self.user_repository: UserRepository = UserRepository()
        self.conversation_repository: ConversationRepository = ConversationRepository()
        self.max_conversations_by_day: int | None = None

    async def create_or_retrieve_user_async(self, user_request_model: UserRequestModel, timeout: int = 10) -> UUID:
        device_info = DeviceInfo(
            ip=user_request_model.IP,
            user_agent=user_request_model.device_info.user_agent,
            platform=user_request_model.device_info.platform,
            app_version=user_request_model.device_info.app_version,
            os=user_request_model.device_info.os,
            browser=user_request_model.device_info.browser,
            is_mobile=user_request_model.device_info.is_mobile
        )
        
        user = User(
            name=user_request_model.user_name,
            device_info=device_info,
            id=user_request_model.user_id,
        )
        
        user_id = await self.user_repository.create_or_update_user_async(user)
        return user_id
    
    async def create_new_conversation_async(self, conversation_request_model: ConversationRequestModel, timeout: int = 10) -> UUID:
        user_id = conversation_request_model.user_id
        recent_conversation_count = await self.conversation_repository.get_recent_conversations_count_by_user_id_async(user_id)
        if self.max_conversations_by_day and recent_conversation_count >= self.max_conversations_by_day: 
            raise QuotaOverloadException("You have reached the maximum number of conversations allowed per day.")
        
        conv_id = conversation_request_model.conversation_id
        new_conversation = await self.conversation_repository.create_new_conversation_empty_async(user_id, conv_id)
        new_conv = await self.conversation_repository.get_conversation_by_id_async(new_conversation.id)
        
        if conversation_request_model.messages and any(conversation_request_model.messages):
            for message_model in conversation_request_model.messages:
                message = Message(
                    role=message_model.role,
                    content=message_model.content,
                    elapsed_seconds=message_model.elapsed_seconds
                )
                new_conv.add_new_message(message.role, message.content)
                await self.conversation_repository.add_message_to_existing_conversation_async(new_conv.id, new_conv.last_message)
        
        return new_conv.id

    async def get_user_last_conversation_async(self, user_id: UUID, timeout: int = 10) -> dict:
        conversations = await self.conversation_repository.get_all_user_conversations_async(user_id)
        if any(conversations):
            last_conversation = conversations[-1]
            return {
                "conversation_id": str(last_conversation.id),
                "user_id": str(user_id),
                "message_count": len(last_conversation.messages) if last_conversation.messages else 0,
                "created_at": last_conversation.created_at.isoformat() if hasattr(last_conversation, 'created_at') else None
            }
        return {"conversation_id": None, "user_id": str(user_id), "message_count": 0}
    
    async def add_message_to_user_last_conversation_or_create_one_async(self, user_id:UUID, new_message:str) -> dict:
        conversations = await self.conversation_repository.get_all_user_conversations_async(user_id)
        if any(conversations):
            conversation = conversations[-1]
        else:
            # Create a new conversation and then get the actual Conversation object
            await self.create_new_conversation_async(
                ConversationRequestModel(user_id=user_id, messages=[])
            )
            # Get the newly created conversation
            conversations = await self.conversation_repository.get_all_user_conversations_async(user_id)
            conversation = conversations[-1] if conversations else None

        if new_message and conversation:
            conversation.add_new_message("user", new_message)
            await self.conversation_repository.add_message_to_existing_conversation_async(conversation.id, conversation.last_message, "user")
        return conversation
    
    async def add_message_to_conversation_async(self, conversation_id: str, new_message: str, role: str = "assistant", timeout: int = 10) -> dict:
        conversation_uuid = UUID(conversation_id)
        conversation = await self.conversation_repository.get_conversation_by_id_async(conversation_uuid)
        if new_message:
            conversation.add_new_message(role, new_message)
            await self.conversation_repository.add_message_to_existing_conversation_async(conversation.id, new_message, role)
        
        return conversation.to_dict()
    