from typing import Any


class Matiere:
    def __init__(self, matiere_id: str, name: str, code: str) -> None:
        self.id = matiere_id
        self.name = name
        self.code = code
        self.modules: list[Any] = []  # List of Module objects

    def add_module(self, module: Any) -> None:
        self.modules.append(module)

    def to_dict(self) -> dict[str, Any]:
        return {"matiere_id": self.id, "name": self.name, "code": self.code, "modules": [module.id for module in self.modules]}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Matiere":
        return Matiere(matiere_id=data["matiere_id"], name=data["name"], code=data["code"])
