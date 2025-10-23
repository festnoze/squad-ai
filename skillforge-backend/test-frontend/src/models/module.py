"""Module model for course content."""


class Module:
    """Represents a module in the course hierarchy."""

    def __init__(self, module_id: str, name: str, code: str, matiere=None) -> None:
        """Initialize a Module instance.

        Args:
            module_id: Unique identifier for the module
            name: Display name of the module
            code: Code/reference for the module
            matiere: Parent Matiere object (optional)
        """
        self.id = module_id
        self.name = name
        self.code = code
        self.matiere = matiere  # Reference to parent Matiere
        self.themes: list = []  # List of Theme objects

    def add_theme(self, theme) -> None:
        """Add a theme to this module."""
        self.themes.append(theme)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "module_id": self.id,
            "name": self.name,
            "code": self.code,
            "matiere_id": self.matiere.id if self.matiere else None,
            "themes": [theme.id for theme in self.themes],
        }

    @staticmethod
    def from_dict(data: dict):
        """Create Module from dictionary."""
        mod = Module(module_id=data["module_id"], name=data["name"], code=data["code"], matiere=None)
        # Save the parent's ID temporarily.
        mod.matiere_id = data.get("matiere_id")
        return mod
