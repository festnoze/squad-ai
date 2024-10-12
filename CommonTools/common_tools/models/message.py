
class Message:
    def __init__(self, role: str, content: str, elapsed_seconds: int = 0) -> None:
        self.role: str = role
        self.content: str = content
        self.elapsed_seconds: int = elapsed_seconds