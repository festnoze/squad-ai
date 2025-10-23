"""Ressource model for course content."""


class Ressource:
    """Represents a resource in the course hierarchy."""

    def __init__(self, ressource_id: str, name: str, code: str, theme=None) -> None:
        """Initialize a Ressource instance.

        Args:
            ressource_id: Unique identifier for the ressource
            name: Display name of the ressource
            code: Code/reference for the ressource
            theme: Parent Theme object (optional)
        """
        self.id = ressource_id
        self.name = name
        self.code = code
        self.theme = theme  # Reference to parent Theme
        self.ressource_objects: list = []  # List of RessourceObject objects

    def add_ressource_object(self, ro) -> None:
        """Add a ressource object to this ressource."""
        self.ressource_objects.append(ro)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "ressource_id": self.id,
            "name": self.name,
            "code": self.code,
            "theme_id": self.theme.id if self.theme else None,
            "ressource_objects": [ro.id for ro in self.ressource_objects],
        }

    @staticmethod
    def from_dict(data: dict):
        """Create Ressource from dictionary."""
        res = Ressource(ressource_id=data["ressource_id"], name=data["name"], code=data["code"], theme=None)
        res.theme_id = data.get("theme_id")
        return res
