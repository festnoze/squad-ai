from typing import Any


class Module:
    def __init__(self, module_id: str, name: str, code: str, matiere: Any | None = None) -> None:
        self.id = module_id
        self.name = name
        self.code = code
        self.matiere = matiere  # Reference to parent Matiere
        self.themes: list[Any] = []  # List of Theme objects

    def add_theme(self, theme: Any) -> None:
        self.themes.append(theme)

    def to_dict(self) -> dict[str, Any]:
        return {"module_id": self.id, "name": self.name, "code": self.code, "matiere_id": self.matiere.id if self.matiere else None, "themes": [theme.id for theme in self.themes]}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Module":
        mod = Module(
            module_id=data["module_id"],
            name=data["name"],
            code=data["code"],
            matiere=None,  # to be linked later
        )
        # Save the parent's ID temporarily.
        setattr(mod, "matiere_id", data.get("matiere_id"))
        return mod
