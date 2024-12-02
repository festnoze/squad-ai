
class Message:
    role: str
    content: str
    elapsed_seconds: int

    def __init__(self, role: str, content: str, elapsed_seconds: int = 0) -> None:
        self.role: str = role
        self.content: str = content
        self.elapsed_seconds: int = elapsed_seconds

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:70]}..."
    
    def __repr__(self) -> str:
        return f"{self.role}: {self.content[:70]}..."