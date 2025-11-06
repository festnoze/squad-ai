from typing import Any


class Ressource:
    def __init__(self, ressource_id: str, name: str, code: str, theme: Any | None = None) -> None:
        self.id = ressource_id
        self.name = name
        self.code = code
        self.theme = theme  # Reference to parent Theme
        self.ressource_objects: list[Any] = []  # List of RessourceObject objects

    def add_ressource_object(self, ro: Any) -> None:
        self.ressource_objects.append(ro)

    def to_dict(self) -> dict[str, Any]:
        return {"ressource_id": self.id, "name": self.name, "code": self.code, "theme_id": self.theme.id if self.theme else None, "ressource_objects": [ro.id for ro in self.ressource_objects]}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Ressource":
        res = Ressource(
            ressource_id=data["ressource_id"],
            name=data["name"],
            code=data["code"],
            theme=None,  # to be linked later
        )
        # Store theme_id temporarily for linking
        setattr(res, "theme_id", data.get("theme_id"))
        return res
