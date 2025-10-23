"""Theme model for course content."""


class Theme:
    """Represents a theme in the course hierarchy."""

    def __init__(self, theme_id: str, name: str, code: str, module=None) -> None:
        """Initialize a Theme instance.

        Args:
            theme_id: Unique identifier for the theme
            name: Display name of the theme
            code: Code/reference for the theme
            module: Parent Module object (optional)
        """
        self.id = theme_id
        self.name = name
        self.code = code
        self.module = module  # Reference to parent Module
        self.ressources: list = []  # List of Ressource objects

    def add_ressource(self, ressource) -> None:
        """Add a ressource to this theme."""
        self.ressources.append(ressource)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "theme_id": self.id,
            "name": self.name,
            "code": self.code,
            "module_id": self.module.id if self.module else None,
            "ressources": [res.id for res in self.ressources],
        }

    @staticmethod
    def from_dict(data: dict):
        """Create Theme from dictionary."""
        th = Theme(theme_id=data["theme_id"], name=data["name"], code=data["code"], module=None)
        th.module_id = data.get("module_id")
        return th
