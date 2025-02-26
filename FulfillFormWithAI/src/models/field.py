from enum import Enum
from typing import Union, Any
import re
from models.validation_models import ValidationError, ValidationResult

class FieldType(Enum):
    INT = 'int'
    STRING = 'string'
    FLOAT = 'float'
    DATE = 'date'
    BOOL = 'bool'

class Field:
    def __init__(self, name: str, description: str, type: str,
            min_size_or_value: Any = None, max_size_or_value: Any = None, regex: str = None, 
            optional: bool = False, validation_func_name: str = None, default_value: str = "") -> None:
        self._value: Any = None
        self.is_validated: Union[bool, None] = None
        self.name: str = name
        self.description: str = description
        self.optional: bool = optional
        self.type: FieldType = FieldType(type)
        self.regex: str = regex
        self.min_size_or_value: Union[int, float] = min_size_or_value
        self.max_size_or_value: Union[int, float] = max_size_or_value
        self.validation_func_name: Any = validation_func_name
        self.default_value: str = default_value

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, new_value: Any) -> None:
        if self.optional and (new_value is None or new_value == "null"):
            self._value = self.default_value
        else:
            self._value = new_value
        result: ValidationResult = self.validate()
        self.is_validated = result.is_valid

    def validate(self) -> ValidationResult:
        errors: list = []
        if self.value is None and not self.optional:
            errors.append(ValidationError("value_missing", "Value is required"))
        if self.value is not None:
            if self.type == FieldType.STRING:
                if not isinstance(self.value, str):
                    errors.append(ValidationError("invalid_type", "Expected type str"))
                else:
                    if self.regex:
                        if not re.match(self.regex, self.value):
                            errors.append(ValidationError("regex_no_match", "Value does not match required pattern", {"regex": self.regex}))
            elif self.type == FieldType.INT:
                if not isinstance(self.value, int):
                    errors.append(ValidationError("invalid_type", "Expected type int"))
                else:
                    if self.min_size_or_value is not None and self.value < self.min_size_or_value:
                        errors.append(ValidationError("min_size_or_value", "Value is below the minimum allowed", {"min_size_or_value": self.min_size_or_value}))
                    if self.max_size_or_value is not None and self.value > self.max_size_or_value:
                        errors.append(ValidationError("max_size_or_value", "Value exceeds the maximum allowed", {"max_size_or_value": self.max_size_or_value}))
            elif self.type == FieldType.FLOAT:
                if not isinstance(self.value, float):
                    errors.append(ValidationError("invalid_type", "Expected type float"))
                else:
                    if self.min_size_or_value is not None and self.value < self.min_size_or_value:
                        errors.append(ValidationError("min_size_or_value", "Value is below the minimum allowed", {"min_size_or_value": self.min_size_or_value}))
                    if self.max_size_or_value is not None and self.value > self.max_size_or_value:
                        errors.append(ValidationError("max_size_or_value", "Value exceeds the maximum allowed", {"max_size_or_value": self.max_size_or_value}))
            elif self.type == FieldType.BOOL:
                if not isinstance(self.value, bool):
                    errors.append(ValidationError("invalid_type", "Expected type bool"))
        result: ValidationResult = ValidationResult(len(errors) == 0, errors)
        self.is_validated = result.is_valid
        return result

    def __str__(self) -> str:
        constraints: list = []
        if self.min_size_or_value is not None:
            constraints.append(f"min_size_or_value={self.min_size_or_value}")
        if self.max_size_or_value is not None:
            constraints.append(f"max_size_or_value={self.max_size_or_value}")
        if self.regex:
            constraints.append(f"regex='{self.regex}'")
        constraints.append("optional=True" if self.optional else "optional=False")
        if self.validation_func_name:
            constraints.append(f"validation_func='{self.validation_func_name}'")
        constraints_str: str = f"{', '.join(constraints)}" if constraints else ""
        return f"◦ Field: {self.name} <{self.type.value}> with constraints: {constraints_str}."