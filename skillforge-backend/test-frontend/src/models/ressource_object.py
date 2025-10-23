"""RessourceObject model for course content."""


class RessourceObject:
    """Represents a resource object (PDF, Opale content, etc.) in the course."""

    def __init__(self, ressource_object_id: str, name: str, resource_type: str, url: str, ressource=None) -> None:
        """Initialize a RessourceObject instance.

        Args:
            ressource_object_id: Unique identifier for the resource object
            name: Display name of the resource object
            resource_type: Type of resource (e.g., 'pdf', 'opale')
            url: URL to access the resource
            ressource: Parent Ressource object (optional)
        """
        self.id = ressource_object_id
        self.name = name
        self.resource_type = resource_type
        self.type = resource_type  # Alias for backward compatibility
        self.url = url
        self.hierarchy: RessourceObjectHierarchy | None = None

    def set_hierarchy(self, hierarchy: "RessourceObjectHierarchy") -> None:
        """Set the hierarchy for this resource object."""
        self.hierarchy = hierarchy

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "ressource_object_id": self.id,
            "name": self.name,
            "resource_type": self.resource_type,
            "url": self.url,
            "hierarchy": self.hierarchy.to_dict() if self.hierarchy else None,
        }

    @staticmethod
    def from_dict(data: dict):
        """Create RessourceObject from dictionary."""
        # Map 'type' from JSON to 'resource_type' in Python (avoid keyword conflict)
        resource_type = data.get("resource_type") or data.get("type")

        ro = RessourceObject(
            ressource_object_id=data["ressource_object_id"],
            name=data["name"],
            resource_type=resource_type,
            url=data["url"],
        )
        ro.ressource_id = data.get("ressource_id")
        if data.get("hierarchy"):
            ro.hierarchy = RessourceObjectHierarchy.from_dict(data["hierarchy"])
        return ro


class RessourceObjectHierarchy:
    """Stores the complete hierarchy context for a resource object."""

    def __init__(self) -> None:
        """Initialize hierarchy with empty parent references."""
        # Only keep parent object references.
        self.ressource = None
        self.theme = None
        self.module = None
        self.matiere = None

    def set_parents(self, ressource, theme, module, matiere) -> None:
        """Set all parent references in the hierarchy."""
        self.ressource = ressource
        self.theme = theme
        self.module = module
        self.matiere = matiere

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "ressource_id": self.ressource.id if self.ressource else None,
            "theme_id": self.theme.id if self.theme else None,
            "module_id": self.module.id if self.module else None,
            "matiere_id": self.matiere.id if self.matiere else None,
        }

    @staticmethod
    def from_dict(data: dict):
        """Create RessourceObjectHierarchy from dictionary."""
        hierarchy = RessourceObjectHierarchy()
        # Temporarily store parent IDs for later linking.
        hierarchy.ressource_id = data.get("ressource_id")
        hierarchy.theme_id = data.get("theme_id")
        hierarchy.module_id = data.get("module_id")
        hierarchy.matiere_id = data.get("matiere_id")
        return hierarchy
