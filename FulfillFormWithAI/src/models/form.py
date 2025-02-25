from models.group import Group

class Form:
    def __init__(self, name: str, groups: list[Group], validation_func: str = None):
        self.name = name
        self.groups = groups
        self.validation_func = validation_func

    def validate(self) -> bool:
        for group in self.groups:
            if not group.validate():
                return False
        if self.validation_func:
            validation_func = getattr(self, self.validation_func, None)
            if validation_func and not validation_func(self):
                return False
        return True
    
    def __str__(self) -> str:
        groups_str = "\n\n".join(str(group) for group in self.groups)
        return f"Form: {self.name}\n{groups_str}"
