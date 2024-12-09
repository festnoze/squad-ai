from datetime import datetime

class Message:
    id: int
    role: str
    content: str
    elapsed_seconds: int
    created_at: datetime

    def __init__(self, role: str, content: str, elapsed_seconds: int = 0, created_at: datetime = None, id: int = None) -> None:
        self.id = id
        self.role = role
        self.content = content
        self.elapsed_seconds = elapsed_seconds
        self.created_at = created_at if created_at else datetime.now(datetime.timezone.utc)

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:70]}..."
    
    def __repr__(self) -> str:
        return f"{self.role}: {self.content[:70]}..."