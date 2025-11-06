from typing import Any


class RessourceObject:
    def __init__(self, ressource_object_id: str, name: str, type: str, url: str, ressource: Any | None = None) -> None:
        self.id = ressource_object_id
        self.name = name
        self.type = type
        self.url = url
        self.hierarchy: "RessourceObjectHierarchy" | None = None

    def set_hierarchy(self, hierarchy: "RessourceObjectHierarchy") -> None:
        self.hierarchy = hierarchy

    def to_dict(self) -> dict[str, Any]:
        return {"ressource_object_id": self.id, "name": self.name, "type": self.type, "url": self.url, "hierarchy": self.hierarchy.to_dict() if self.hierarchy else None}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "RessourceObject":
        ro = RessourceObject(
            ressource_object_id=data["ressource_object_id"],
            name=data["name"],
            type=data["type"],
            url=data["url"],
        )
        # Store ressource_id temporarily for linking
        setattr(ro, "ressource_id", data.get("ressource_id"))
        if data.get("hierarchy"):
            ro.hierarchy = RessourceObjectHierarchy.from_dict(data["hierarchy"])
        return ro


class RessourceObjectHierarchy:
    def __init__(self) -> None:
        # Only keep parent object references.
        self.ressource: Any | None = None
        self.theme: Any | None = None
        self.module: Any | None = None
        self.matiere: Any | None = None

    def set_parents(self, ressource: Any, theme: Any, module: Any, matiere: Any) -> None:
        self.ressource = ressource
        self.theme = theme
        self.module = module
        self.matiere = matiere

    def to_dict(self) -> dict[str, str | None]:
        return {
            "ressource_id": self.ressource.id if self.ressource else None,
            "theme_id": self.theme.id if self.theme else None,
            "module_id": self.module.id if self.module else None,
            "matiere_id": self.matiere.id if self.matiere else None,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "RessourceObjectHierarchy":
        hierarchy = RessourceObjectHierarchy()
        # Temporarily store parent IDs for later linking.
        setattr(hierarchy, "ressource_id", data.get("ressource_id"))
        setattr(hierarchy, "theme_id", data.get("theme_id"))
        setattr(hierarchy, "module_id", data.get("module_id"))
        setattr(hierarchy, "matiere_id", data.get("matiere_id"))
        return hierarchy
