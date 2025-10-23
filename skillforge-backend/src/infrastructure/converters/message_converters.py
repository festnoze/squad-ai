from datetime import timezone
from uuid import UUID
from infrastructure.entities.message_entity import MessageEntity
from infrastructure.converters.role_converters import RoleConverters
from models.message import Message


class MessageConverters:
    @staticmethod
    def convert_message_entity_to_model(message_entity: MessageEntity) -> Message:
        """Convert a MessageEntity to a Message model.

        Args:
            message_entity: The database entity to convert

        Returns:
            Message model instance with timezone-aware datetimes
        """
        return Message(
            id=message_entity.id,
            thread_id=message_entity.thread_id,
            role=RoleConverters.convert_role_entity_to_model(message_entity.role),
            content=message_entity.content,
            elapsed_seconds=message_entity.elapsed_seconds,
            created_at=message_entity.created_at.replace(tzinfo=timezone.utc),
            updated_at=message_entity.updated_at.replace(tzinfo=timezone.utc) if message_entity.updated_at else None,
            deleted_at=message_entity.deleted_at.replace(tzinfo=timezone.utc) if message_entity.deleted_at else None,
        )

    @staticmethod
    def convert_message_model_to_entity(message: Message, thread_id: UUID | None = None) -> MessageEntity:
        """Convert a Message model to a MessageEntity.

        Args:
            message: The Message model to convert
            thread_id: Optional thread_id to override the one in the message

        Returns:
            MessageEntity instance with timezone-naive datetimes (for database storage)
        """
        return MessageEntity(
            id=message.id,
            thread_id=thread_id or message.thread_id,
            role_id=message.role.id,
            content=message.content,
            elapsed_seconds=message.elapsed_seconds,
            created_at=message.created_at.replace(tzinfo=None) if message.created_at else None,
            updated_at=message.updated_at.replace(tzinfo=None) if message.updated_at else None,
            deleted_at=message.deleted_at.replace(tzinfo=None) if message.deleted_at else None,
        )
