from uuid import UUID
from models.base_model import IdStatefulBaseModel
from models.message import Message


class Thread(IdStatefulBaseModel):
    """Thread model representing a conversation thread.

    Inherits common fields (id, created_at, updated_at, deleted_at) from BaseModelWithTimestamps.

    Attributes:
        user_id: UUID of the user who owns this thread
        context_id: UUID of the context associated with this thread (optional)
        messages: List of messages in the thread
    """

    user_id: UUID | None = None
    context_id: UUID | None = None
    messages: list[Message] = []
