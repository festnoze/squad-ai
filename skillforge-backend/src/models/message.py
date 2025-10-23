from uuid import UUID
from models.base_model import IdStatefulBaseModel
from models.role import Role


class Message(IdStatefulBaseModel):
    """Message model representing a single message in a thread.

    Inherits common fields (id, created_at, updated_at, deleted_at) from BaseModelWithTimestamps.

    Attributes:
        thread_id: UUID of the thread this message belongs to
        role: Role of the message sender (user, assistant, etc.)
        content: Text content of the message
        elapsed_seconds: Time elapsed for message processing (default: 0)
    """

    thread_id: UUID
    role: Role
    content: str
    elapsed_seconds: int = 0
