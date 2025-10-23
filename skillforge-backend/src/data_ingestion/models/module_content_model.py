class Module:
    def __init__(self, module_id, name, code, matiere=None):
        self.id = module_id
        self.name = name
        self.code = code
        self.matiere = matiere  # Reference to parent Matiere
        self.themes = []  # List of Theme objects

    def add_theme(self, theme):
        self.themes.append(theme)

    def to_dict(self):
        return {"module_id": self.id, "name": self.name, "code": self.code, "matiere_id": self.matiere.id if self.matiere else None, "themes": [theme.id for theme in self.themes]}

    @staticmethod
    def from_dict(data):
        mod = Module(
            module_id=data["module_id"],
            name=data["name"],
            code=data["code"],
            matiere=None,  # to be linked later
        )
        # Save the parent's ID temporarily.
        mod.matiere_id = data.get("matiere_id")
        return mod
