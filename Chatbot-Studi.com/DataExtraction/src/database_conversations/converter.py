from database_conversations.entities import ConversationEntity, MessageEntity, UserEntity
from common_tools.models.conversation import Conversation
from common_tools.models.message import Message
from common_tools.models.user import User
from uuid import UUID

class ConversationConverter:
    @staticmethod
    def convert_user_entity_to_model(user_entity: UserEntity) -> User:
        return User(
            id=user_entity.id,
            name=user_entity.name,
            ip=user_entity.ip,
            device_info=user_entity.device_info,
            created_at=user_entity.created_at
        )

    @staticmethod
    def convert_user_model_to_entity(user: User) -> UserEntity:
        return UserEntity(
            id=user.id,
            name=user.name,
            ip=user.ip,
            device_info=user.device_info,
            created_at=user.created_at
        )

    @staticmethod
    def convert_message_entity_to_model(message_entity: MessageEntity) -> Message:
        return Message(
            id=message_entity.id,
            role=message_entity.role,
            content=message_entity.content,
            elapsed_seconds=message_entity.elapsed_seconds,
            created_at=message_entity.created_at
        )

    @staticmethod
    def convert_message_model_to_entity(message: Message, conversation_id: UUID) -> MessageEntity:
        return MessageEntity(
            role=message.role,
            content=message.content,
            elapsed_seconds=message.elapsed_seconds,
            created_at=message.created_at,
            conversation_id=conversation_id
        )

    @staticmethod
    def convert_conversation_entity_to_model(conversation_entity: ConversationEntity) -> Conversation:
        user_model = ConversationConverter.convert_user_entity_to_model(conversation_entity.user)
        messages = [
            ConversationConverter.convert_message_entity_to_model(message)
            for message in conversation_entity.messages
        ]
        return Conversation(
            id=conversation_entity.id,
            user=user_model,
            messages=messages,
            created_at=conversation_entity.created_at
        )

    @staticmethod
    def convert_conversation_model_to_entity(conversation: Conversation) -> ConversationEntity:
        user_entity = ConversationConverter.convert_user_model_to_entity(conversation.user)
        messages = [
            ConversationConverter.convert_message_model_to_entity(message, conversation.id)
            for message in conversation.messages
        ]
        return ConversationEntity(
            id=conversation.id,
            user=user_entity,
            messages=messages,
            created_at=conversation.created_at
        )
