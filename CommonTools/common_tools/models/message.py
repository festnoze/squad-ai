from datetime import datetime
import uuid
from uuid import UUID

class Message:
    id: UUID
    role: str
    content: str
    elapsed_seconds: int
    created_at: datetime

    def __init__(self, role: str, content: str, elapsed_seconds: int = 0, id: UUID = None, created_at: datetime = None) -> None:
        self.id = id if id is not None else uuid.uuid4()
        self.role = role
        self.content = content
        self.elapsed_seconds = elapsed_seconds
        self.created_at = created_at

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:70]}..."
    
    def __repr__(self) -> str:
        return f"{self.role}: {self.content[:70]}..."