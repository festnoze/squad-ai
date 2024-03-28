class StreamContainer:
    def __init__(self, content=""):
        self.content = content

    def add_content(self, new_content: str):
        """Appends new content to the existing content."""
        self.content += new_content
