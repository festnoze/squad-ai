from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


class RoleResponse(BaseModel):
    """Response model for Role information.

    Attributes:
        id: Unique identifier (UUID)
        name: Role name (e.g., 'user', 'assistant')
    """

    id: UUID
    name: str


class MessageResponse(BaseModel):
    """Response model for Message information.

    Attributes:
        id: Unique identifier (UUID)
        thread_id: UUID of the thread this message belongs to
        role: Role of the message sender
        content: Text content of the message
        elapsed_seconds: Time elapsed for message processing
        created_at: Timestamp when the record was created
        updated_at: Timestamp when the record was last updated
        deleted_at: Timestamp when the record was soft-deleted
    """

    id: UUID | None = None
    thread_id: UUID
    role: RoleResponse
    content: str
    elapsed_seconds: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class ThreadResponse(BaseModel):
    """Response model for Thread information.

    Attributes:
        id: Unique identifier (UUID)
        user_id: UUID of the user who owns this thread
        messages: List of messages in the thread
        created_at: Timestamp when the record was created
        updated_at: Timestamp when the record was last updated
        deleted_at: Timestamp when the record was soft-deleted
    """

    id: UUID | None = None
    user_id: UUID | None = None
    messages: list[MessageResponse] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class ThreadCreatedResponse(BaseModel):
    """Response model for thread creation.

    Attributes:
        message: Success message
        thread_id: ID of the created thread
    """

    message: str
    thread_id: str


class ThreadIdsResponse(BaseModel):
    """Response model for thread IDs list.

    Attributes:
        threads_ids: List of thread IDs
    """

    threads_ids: list[str]


class ThreadMessagesResponse(BaseModel):
    """Response model for thread messages with pagination info.

    Attributes:
        thread_id: ID of the thread
        messages_count: Total number of messages in the thread
        messages: List of messages (paginated)
    """

    thread_id: str
    messages_count: int
    messages: list[MessageResponse]
