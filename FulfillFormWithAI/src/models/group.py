from models.field import Field

class Group:
    def __init__(self, name: str, fields: list[Field], validation_func: str = None):
        self.name = name
        self.fields = fields
        self.validation_func = validation_func

    def validate(self) -> bool:
        for field in self.fields:
            if field.validation_func_name:
                validation_func = getattr(self, field.validation_func_name, None)
                if validation_func and not validation_func():
                    return False
            if not field.validate():
                return False
            
        if self.validation_func:
            validation_func = getattr(self, self.validation_func, None)
            if validation_func and not validation_func():
                return False
        return True
    
    def __str__(self) -> str:
        fields_str = "\n    " + "\n    ".join(str(field) for field in self.fields)
        return f"  • Group: {self.name}{fields_str}"
