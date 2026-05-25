"""Repository for the `chat_messages` table."""

from uuid import UUID

from app.infrastructure.base_repository import BaseRepository
from app.infrastructure.converters.chat_message_converters import (
    ChatMessageConverters,
)
from app.infrastructure.entities.chat_message_entity import ChatMessageEntity
from app.models.chat_message import ChatMessage


class ChatMessageRepository(BaseRepository):
    """Domain-friendly facade around `ChatMessageEntity`.

    All public methods exchange Pydantic `ChatMessage` models — SQLAlchemy
    entities never leak out of this class.
    """

    async def acreate_message(self, message: ChatMessage) -> ChatMessage:
        """Persist a new chat message and return the stored model."""
        entity = ChatMessageConverters.convert_chat_message_model_to_entity(message)
        entity = await self.aadd_entity(entity)
        return ChatMessageConverters.convert_chat_message_entity_to_model(entity)

    async def aget_message_by_id(
        self,
        message_id: UUID,
    ) -> ChatMessage | None:
        """Fetch a chat message by id, excluding soft-deleted rows."""
        entity = await self.aget_entity_by_id(ChatMessageEntity, message_id)
        if entity is None:
            return None
        return ChatMessageConverters.convert_chat_message_entity_to_model(entity)

    async def aget_messages_by_project(
        self,
        project_id: UUID,
    ) -> list[ChatMessage]:
        """Return every message in a project, oldest first.

        Messages are ordered by `created_at` ascending so the caller can
        stream them as a conversation transcript.
        """
        entities = await self.aget_all_entities(
            ChatMessageEntity,
            filters=[ChatMessageEntity.project_id == project_id],
            order_by=ChatMessageEntity.created_at.asc(),
        )
        return [
            ChatMessageConverters.convert_chat_message_entity_to_model(entity)
            for entity in entities
        ]
