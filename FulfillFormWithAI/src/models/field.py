from enum import Enum

class FieldType(Enum):
    INT = 'int'
    STRING = 'string'
    FLOAT = 'float'
    DATE = 'date'
    BOOL = 'bool'

class Field:
    def __init__(self, name: str, description: str, type: str,
                 min_size_or_value: any = None, max_size_or_value: any = None, regex: str = None, 
                 optional: bool = False, validation_func_name: str = None):
        self.name:str = name
        self.description:str = description
        self.type:FieldType = FieldType(type)
        self.min_size_or_value:int = min_size_or_value
        self.max_size_or_value:int = max_size_or_value
        self.regex:str = regex
        self.optional:bool = optional
        self.validation_func_name:str = validation_func_name
        self.value = None

    def __str__(self) -> str:
        constraints = []
        if self.min_size_or_value is not None:
            constraints.append(f"min_size_or_value={self.min_size_or_value}")
        if self.max_size_or_value is not None:
            constraints.append(f"max_size_or_value={self.max_size_or_value}")
        if self.regex:
            constraints.append(f"regex='{self.regex}'")
        
        constraints.append("optional=True" if self.optional else "optional=False")

        if self.validation_func_name:
            constraints.append(f"validation_func='{self.validation_func_name}'")

        constraints_str = f" ({', '.join(constraints)})" if constraints else ""
        return f"◦ Field: {self.name}:{self.type.value} with: {constraints_str}"
    
    def validate(self) -> bool:
        if self.value is None and not self.optional:
            return False

        if self.value is not None:
            if self.type == FieldType.STRING:
                if not isinstance(self.value, str):
                    return False
                if self.max_size and len(self.value) > self.max_size:
                    return False
                if self.regex:
                    import re
                    if not re.match(self.regex, self.value):
                        return False

            elif self.type == FieldType.INT:
                if not isinstance(self.value, int):
                    return False
                if self.min_value is not None and self.value < self.min_value:
                    return False
                if self.max_value is not None and self.value > self.max_value:
                    return False

            elif self.type == FieldType.FLOAT:
                if not isinstance(self.value, float):
                    return False
                if self.min_value is not None and self.value < self.min_value:
                    return False
                if self.max_value is not None and self.value > self.max_value:
                    return False

            elif self.type == FieldType.BOOL:
                if not isinstance(self.value, bool):
                    return False

        return True