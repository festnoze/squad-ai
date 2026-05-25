"""Bidirectional converters between `ChatMessageEntity` and `ChatMessage`."""

from app.infrastructure.entities.chat_message_entity import ChatMessageEntity
from app.models.chat_message import ChatMessage, ChatMessageRole


class ChatMessageConverters:
    """Static helpers to keep the domain layer free of SQLAlchemy leaks."""

    @staticmethod
    def convert_chat_message_entity_to_model(
        entity: ChatMessageEntity,
    ) -> ChatMessage:
        """Convert a SQLAlchemy entity into a Pydantic domain model."""
        return ChatMessage(
            id=entity.id,
            project_id=entity.project_id,
            role=ChatMessageRole(entity.role),
            content=entity.content,
            meta_data=entity.meta_data,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            deleted_at=entity.deleted_at,
        )

    @staticmethod
    def convert_chat_message_model_to_entity(
        model: ChatMessage,
    ) -> ChatMessageEntity:
        """Convert a Pydantic domain model into a SQLAlchemy entity.

        Only populates fields that are not None so that the database's
        default values (e.g. `created_at`) can kick in for fresh inserts.
        """
        entity = ChatMessageEntity(
            project_id=model.project_id,
            role=model.role.value,
            content=model.content,
            meta_data=model.meta_data,
        )
        if model.id is not None:
            entity.id = model.id
        if model.created_at is not None:
            entity.created_at = model.created_at
        if model.updated_at is not None:
            entity.updated_at = model.updated_at
        if model.deleted_at is not None:
            entity.deleted_at = model.deleted_at
        return entity
