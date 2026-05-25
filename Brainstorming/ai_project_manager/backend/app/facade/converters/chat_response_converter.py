"""Converters between chat/scoping domain models and HTTP response models."""

from app.facade.response_models.chat_response import (
    ChatMessageResponse,
    ItemResponse,
    SendMessageResponse,
)
from app.models.chat_message import ChatMessage
from app.models.item import Item
from app.services.scoping_agent import ScopingResult


class ChatResponseConverter:
    """Static helpers bridging the chat domain layer and the HTTP facade."""

    @staticmethod
    def convert_chat_message_to_response(
        msg: ChatMessage,
    ) -> ChatMessageResponse:
        """Convert a single `ChatMessage` into its `ChatMessageResponse`."""
        if msg.id is None or msg.created_at is None:
            raise ValueError(
                "Cannot serialize a chat message missing id/created_at — "
                "this should never happen for a persisted message.",
            )
        return ChatMessageResponse(
            id=msg.id,
            project_id=msg.project_id,
            role=msg.role.value,
            content=msg.content,
            meta_data=msg.meta_data,
            created_at=msg.created_at,
        )

    @staticmethod
    def convert_chat_messages_to_responses(
        messages: list[ChatMessage],
    ) -> list[ChatMessageResponse]:
        """Convert a list of `ChatMessage` into their response views."""
        return [
            ChatResponseConverter.convert_chat_message_to_response(msg)
            for msg in messages
        ]

    @staticmethod
    def convert_item_to_response(item: Item) -> ItemResponse:
        """Convert a single `Item` into its `ItemResponse`."""
        if item.id is None or item.created_at is None:
            raise ValueError(
                "Cannot serialize an item missing id/created_at — "
                "this should never happen for a persisted item.",
            )
        return ItemResponse(
            id=item.id,
            project_id=item.project_id,
            parent_id=item.parent_id,
            type=item.type.value,
            title=item.title,
            description=item.description,
            complexity=(
                item.complexity.value if item.complexity is not None else None
            ),
            status=item.status.value,
            acceptance_criteria=item.acceptance_criteria,
            order=item.order,
            deliverable_paths=item.deliverable_paths,
            deliverable_notes=item.deliverable_notes,
            blocked_reason=item.blocked_reason,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def convert_items_to_responses(items: list[Item]) -> list[ItemResponse]:
        """Convert a list of `Item` into their response views."""
        return [
            ChatResponseConverter.convert_item_to_response(item)
            for item in items
        ]

    @staticmethod
    def convert_scoping_result_to_response(
        result: ScopingResult,
    ) -> SendMessageResponse:
        """Convert a `ScopingResult` into a `SendMessageResponse` envelope."""
        return SendMessageResponse(
            message=ChatResponseConverter.convert_chat_message_to_response(
                result.assistant_message,
            ),
            items_created=ChatResponseConverter.convert_items_to_responses(
                result.items_created,
            ),
            items_updated=ChatResponseConverter.convert_items_to_responses(
                result.items_updated,
            ),
            action=result.action,
        )
