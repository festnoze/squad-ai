from datetime import datetime, timezone
import uuid
from uuid import UUID
from database.models.conversation import Conversation
from database.models.message import Message
from database.models.user import User
from database.models.device_info import DeviceInfo

from database.entities import ConversationEntity, MessageEntity, UserEntity, DeviceInfoEntity

class ConversationEntityToDtoConverter:
    @staticmethod
    def convert_device_info_entity_to_model(device_info_entity: DeviceInfoEntity) -> DeviceInfo:
        return DeviceInfo(
            ip=device_info_entity.ip,
            user_agent=device_info_entity.user_agent,
            platform=device_info_entity.platform,
            app_version=device_info_entity.app_version,
            os=device_info_entity.os,
            browser=device_info_entity.browser,
            is_mobile=device_info_entity.is_mobile,
            created_at=device_info_entity.created_at,
            id=device_info_entity.id,
        )

    @staticmethod
    def convert_device_info_model_to_entity(device_info: DeviceInfo) -> DeviceInfoEntity:
        entity = DeviceInfoEntity(
            ip=device_info.ip,
            user_agent=device_info.user_agent,
            platform=device_info.platform,
            app_version=device_info.app_version,
            os=device_info.os,
            browser=device_info.browser,
            is_mobile=device_info.is_mobile,
            created_at=device_info.created_at if device_info.created_at else datetime.now(timezone.utc)
        )
        if device_info.id: entity.id = device_info.id
        return entity
    
    @staticmethod
    def convert_user_entity_to_model(user_entity: UserEntity) -> User:
        return User(
            name=user_entity.name,
            device_info=ConversationEntityToDtoConverter.convert_device_info_entity_to_model(user_entity.device_infos[-1]) if user_entity.device_infos and any(user_entity.device_infos) else None,
            id=user_entity.id,
            created_at=user_entity.created_at,
        )

    @staticmethod
    def convert_user_model_to_entity(user: User) -> UserEntity:
        if user.id is None: user.id = uuid.uuid4()

        new_user_entity = UserEntity(
            name=user.name,
            created_at=user.created_at if user.created_at else datetime.now(timezone.utc),
            id=user.id,
        )
        if user.id: new_user_entity.id=user.id

        return new_user_entity

    @staticmethod
    def convert_message_entity_to_model(message_entity: MessageEntity) -> Message:
        return Message(
            role=message_entity.role,
            content=message_entity.content,
            elapsed_seconds=message_entity.elapsed_seconds,
            id=message_entity.id,
            created_at=message_entity.created_at
        )

    @staticmethod
    def convert_message_model_to_entity(message: Message, conversation_id: UUID) -> MessageEntity:
        entity = MessageEntity(
            conversation_id=conversation_id,
            role=message.role,
            content=message.content,
            elapsed_seconds=message.elapsed_seconds,
            created_at=message.created_at if message.created_at else datetime.now(timezone.utc)
        )
        if message.id: entity.id=message.id
        return entity

    @staticmethod
    def convert_conversation_entity_to_model(conversation_entity: ConversationEntity) -> Conversation:
        if not conversation_entity: return None
        user_model = ConversationEntityToDtoConverter.convert_user_entity_to_model(conversation_entity.user)
        
        # Sorted messages by ascending creation order
        sorted_messages_entities = sorted(conversation_entity.messages, key=lambda msg: msg.created_at)
        sorted_messages = [
          ConversationEntityToDtoConverter.convert_message_entity_to_model(message)
          for message in sorted_messages_entities  
        ]
        return Conversation(
            user=user_model,
            messages=sorted_messages,
            id=conversation_entity.id,
            created_at=conversation_entity.created_at
        )

    @staticmethod
    def convert_conversation_model_to_entity(conversation: Conversation) -> ConversationEntity:
        entity = ConversationEntity(
            user_id=conversation.user.id if conversation.user and conversation.user.id else None,
            created_at=conversation.created_at if conversation.created_at else datetime.now(timezone.utc),
        )
        if conversation.id: entity.id=conversation.id

        entity.messages=[
                ConversationEntityToDtoConverter.convert_message_model_to_entity(message, conversation.id)
                for message in conversation.messages
            ]
        return entity
