from datetime import datetime, timezone
from src.database_conversations.entities import ConversationEntity, MessageEntity, UserEntity
from common_tools.models.conversation import Conversation
from common_tools.models.message import Message
from common_tools.models.user import User
from uuid import UUID

class ConversationConverters:
    @staticmethod
    def convert_user_entity_to_model(user_entity: UserEntity) -> User:
        return User(
            name=user_entity.name,
            ip=user_entity.ip,
            device_info=user_entity.device_info,
            created_at=user_entity.created_at,
            id=user_entity.id,
        )

    @staticmethod
    def convert_user_model_to_entity(user: User) -> UserEntity:
        return UserEntity(
            name=user.name,
            ip=user.ip,
            device_info=user.device_info,
            id=user.id,
            created_at=user.created_at if user.created_at else datetime.now(timezone.utc)
        )

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
        return MessageEntity(
            conversation_id=conversation_id,
            role=message.role,
            content=message.content,
            elapsed_seconds=message.elapsed_seconds,
            id=message.id,
            created_at=message.created_at if message.created_at else datetime.now(timezone.utc)
        )

    @staticmethod
    def convert_conversation_entity_to_model(conversation_entity: ConversationEntity) -> Conversation:
        if not conversation_entity: return None
        user_model = ConversationConverters.convert_user_entity_to_model(conversation_entity.user)
        messages = [
            ConversationConverters.convert_message_entity_to_model(message)
            for message in conversation_entity.messages
        ]
        return Conversation(
            user=user_model,
            messages=messages,
            id=conversation_entity.id,
            created_at=conversation_entity.created_at
        )

    @staticmethod
    def convert_conversation_model_to_entity(conversation: Conversation) -> ConversationEntity:
        entity = ConversationEntity(
            id=conversation.id,
            user_id=conversation.user.id,
            created_at=conversation.created_at if conversation.created_at else datetime.now(timezone.utc),
        )
        entity.messages=[
                ConversationConverters.convert_message_model_to_entity(message, conversation.id)
                for message in conversation.messages
            ]
        return entity
