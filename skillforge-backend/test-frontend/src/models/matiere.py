"""Matiere (Subject) model for course content."""


class Matiere:
    """Represents a subject/matiere in the course hierarchy."""

    def __init__(self, matiere_id: str, name: str, code: str) -> None:
        """Initialize a Matiere instance.

        Args:
            matiere_id: Unique identifier for the matiere
            name: Display name of the matiere
            code: Code/reference for the matiere
        """
        self.id = matiere_id
        self.name = name
        self.code = code
        self.modules: list = []  # List of Module objects

    def add_module(self, module) -> None:
        """Add a module to this matiere."""
        self.modules.append(module)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "matiere_id": self.id,
            "name": self.name,
            "code": self.code,
            "modules": [module.id for module in self.modules],
        }

    @staticmethod
    def from_dict(data: dict):
        """Create Matiere from dictionary."""
        return Matiere(matiere_id=data["matiere_id"], name=data["name"], code=data["code"])
