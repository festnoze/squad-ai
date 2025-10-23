from models.thread import Thread
from models.message import Message
from models.role import Role
from facade.response_models.thread_response import (
    ThreadResponse,
    MessageResponse,
    RoleResponse,
    ThreadCreatedResponse,
    ThreadIdsResponse,
    ThreadMessagesResponse,
)


class ThreadResponseConverter:
    """Converter for transforming domain models to thread response models."""

    @staticmethod
    def convert_thread_to_response(thread: Thread) -> ThreadResponse:
        """Convert Thread domain model to ThreadResponse.

        Args:
            thread: The domain model containing thread information

        Returns:
            ThreadResponse model for API response
        """
        messages_response = [ThreadResponseConverter.convert_message_to_response(msg) for msg in thread.messages]

        return ThreadResponse(
            id=thread.id,
            user_id=thread.user_id,
            messages=messages_response,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            deleted_at=thread.deleted_at,
        )

    @staticmethod
    def convert_message_to_response(message: Message) -> MessageResponse:
        """Convert Message domain model to MessageResponse.

        Args:
            message: The domain model containing message information

        Returns:
            MessageResponse model for API response
        """
        role_response = ThreadResponseConverter.convert_role_to_response(message.role)

        return MessageResponse(
            id=message.id,
            thread_id=message.thread_id,
            role=role_response,
            content=message.content,
            elapsed_seconds=message.elapsed_seconds,
            created_at=message.created_at,
            updated_at=message.updated_at,
            deleted_at=message.deleted_at,
        )

    @staticmethod
    def convert_role_to_response(role: Role) -> RoleResponse:
        """Convert Role domain model to RoleResponse.

        Args:
            role: The domain model containing role information

        Returns:
            RoleResponse model for API response
        """
        return RoleResponse(id=role.id, name=role.name)

    @staticmethod
    def convert_thread_to_created_response(thread: Thread) -> ThreadCreatedResponse:
        """Convert Thread to ThreadCreatedResponse for creation endpoint.

        Args:
            thread: The domain model containing thread information

        Returns:
            ThreadCreatedResponse model for API response
        """
        return ThreadCreatedResponse(message="Thread created successfully", thread_id=str(thread.id))

    @staticmethod
    def convert_thread_ids_to_response(thread_ids: list) -> ThreadIdsResponse:
        """Convert list of thread IDs to ThreadIdsResponse.

        Args:
            thread_ids: List of thread UUIDs

        Returns:
            ThreadIdsResponse model for API response
        """
        return ThreadIdsResponse(threads_ids=[str(thread_id) for thread_id in thread_ids])

    @staticmethod
    def convert_thread_to_messages_response(thread: Thread, start_index: int = 0, end_index: int | None = None, total_messages_count: int | None = None) -> ThreadMessagesResponse:
        """Convert Thread to ThreadMessagesResponse with pagination.

        Args:
            thread: The domain model containing thread information
            start_index: Starting index for pagination
            end_index: Ending index for pagination (None for all remaining messages)
            total_messages_count: Total count of messages in the thread (for pagination metadata). If None, uses len(thread.messages)

        Returns:
            ThreadMessagesResponse model for API response
        """
        if end_index is None:
            end_index = len(thread.messages)

        paginated_messages = thread.messages[start_index:end_index]
        messages_response = [ThreadResponseConverter.convert_message_to_response(msg) for msg in paginated_messages]

        # Use total_messages_count if provided, otherwise fall back to len(thread.messages)
        messages_count = total_messages_count if total_messages_count is not None else len(thread.messages)

        return ThreadMessagesResponse(thread_id=str(thread.id), messages_count=messages_count, messages=messages_response)
