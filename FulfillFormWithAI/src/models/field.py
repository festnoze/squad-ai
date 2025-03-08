from enum import Enum
import re
from typing import Union
from models.validation_models import ValidationError, ValidationResult

class FieldType(Enum):
    INT = 'int'
    STRING = 'string'
    FLOAT = 'float'
    DATE = 'date'
    BOOL = 'bool'

class Field:
    def __init__(self, name: str, description: str, type: str, min_size_or_value: any = None, max_size_or_value: any = None, regex: str = None,
            regex_description: str = None, optional: bool = False, default_value: str = None, allowed_values: list[str] = None, validation_func_name: str = None) -> None:      
        self.name: str = name
        self.description: str = description
        self.optional: bool = optional
        self.type: FieldType = FieldType(type)
        self.regex: str = regex
        self.regex_description = regex_description
        self.min_size_or_value: Union[int, float] = min_size_or_value
        self.max_size_or_value: Union[int, float] = max_size_or_value
        self.validation_func_name: any = validation_func_name
        self.default_value: str = default_value
        self.allowed_values: list[Union[str|list[str]]] = allowed_values
        #
        self._value: any = None
        self.is_validated: Union[bool, None] = None
        self.group_name: str = None

    @property
    def value(self) -> any:
        return self._value

    @value.setter
    def value(self, new_value: any) -> None:
        if (new_value is None or new_value == "null"):
            if not self.optional: 
                raise ValueError("Value is required because the field is flagged as not-optional")
            self._value = self.default_value
        else:
            self._value = self.normalize_value(new_value)

        self.is_validated = self.validate().is_valid
        
    def validate(self) -> ValidationResult:
        errors: list = []
        
        if not self.value and not self.optional:
            errors.append(ValidationError("value_missing", "Value is required"))

        if self.value:
            valid_values = [item[0] if isinstance(item, list) else item for item in self.allowed_values] if self.allowed_values else None
            
            if self.allowed_values and self.value not in valid_values:
                errors.append(ValidationError("invalid_value", "Value do not belongs to allowed values", {"provided_value": self.value, "allowed_values": self.allowed_values}))
            
            if self.type == FieldType.STRING:
                if not isinstance(self.value, str):
                    errors.append(ValidationError("invalid_type", "Expected type str"))
                else:
                    if self.regex and not re.match(self.regex, self.value):
                        errors.append(ValidationError("regex_no_match", f"Value does not match the following required pattern: {self.regex_description if self.regex_description else self.regex}", {"provided_value": self.value, "regex": self.regex, "regex_description": self.regex_description}))
            
            elif self.type == FieldType.INT:
                if not isinstance(self.value, int):
                    errors.append(ValidationError("invalid_type", "Expected type int"))
                else:
                    if self.min_size_or_value and self.value < self.min_size_or_value:
                        errors.append(ValidationError("min_size_or_value", "Value is below the minimum allowed", {"provided_value": self.value, "min_size_or_value": self.min_size_or_value}))
                    if self.max_size_or_value and self.value > self.max_size_or_value:
                        errors.append(ValidationError("max_size_or_value", "Value exceeds the maximum allowed", {"provided_value": self.value, "max_size_or_value": self.max_size_or_value}))
            
            elif self.type == FieldType.FLOAT:
                if not isinstance(self.value, float):
                    errors.append(ValidationError("invalid_type", "Expected type float"))
                else:
                    if self.min_size_or_value and self.value < self.min_size_or_value:
                        errors.append(ValidationError("min_size_or_value", "Value is below the minimum allowed", {"provided_value": self.value, "min_size_or_value": self.min_size_or_value}))
                    if self.max_size_or_value and self.value > self.max_size_or_value:
                        errors.append(ValidationError("max_size_or_value", "Value exceeds the maximum allowed", {"provided_value": self.value, "max_size_or_value": self.max_size_or_value}))
            
            elif self.type == FieldType.BOOL:
                if not isinstance(self.value, bool):
                    errors.append(ValidationError("invalid_type", "Expected type bool"))
        
        result: ValidationResult = ValidationResult(len(errors) == 0, errors)
        self.is_validated = result.is_valid
        return result

    def normalize_value(self, input_value: any) -> any:
        "if allowed_values is defined, return the first value that matches the input_value"
        if self.allowed_values:
            input_value_lower = str(input_value).lower()
            for allowed in self.allowed_values:
                if isinstance(allowed, list):
                    if input_value_lower in map(str.lower, allowed):
                        return allowed[0]
                elif isinstance(allowed, str) and input_value_lower == allowed.lower():
                    return allowed
        return input_value
    
    def __str__(self) -> str:
        constraints: list = []
        if self.min_size_or_value:
            constraints.append(f"min_size_or_value= {self.min_size_or_value}")
        if self.max_size_or_value:
            constraints.append(f"max_size_or_value= {self.max_size_or_value}")
        if self.regex:
            regex_description = f" ({self.regex_description})" if self.regex_description else ""
            constraints.append(f"regex= '{self.regex}'{regex_description}")
        constraints.append("optional= True" if self.optional else "optional=False")
        if self.default_value:
            constraints.append(f"default_value= '{self.default_value}'")
        if self.validation_func_name:
            constraints.append(f"validation_func= '{self.validation_func_name}'")
        if self.allowed_values:
            formatted_values = [f"{' or '.join(av) if isinstance(av, list) else av}" for av in self.allowed_values]
            constraints.append(f"allowed_values={', '.join(formatted_values)}")
        constraints_str: str = f"{', '.join(constraints)}" if constraints else ""
        return f"◦ Field: {self.name} <{self.type.value}>{f" = '{self.value}'" if self.value else ""} with constraints: {constraints_str}."
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "optional": self.optional,
            "type": self.type.value,
            "group_name": self.group_name,
            "regex": self.regex,
            "regex_description": self.regex_description,
            "min_size_or_value": self.min_size_or_value,
            "max_size_or_value": self.max_size_or_value,
            "validation_func_name": self.validation_func_name,
            "default_value": self.default_value,
            "allowed_values": self.allowed_values,
            "value": self._value,
            "is_validated": self.is_validated,
        }
    
    @staticmethod
    def from_dict(field_dict: dict) -> 'Field':
        field = Field(
            name=field_dict['name'],
            description=field_dict.get('description'),
            type=field_dict['type'],
            min_size_or_value=field_dict.get('min_size_or_value'),
            max_size_or_value=field_dict.get('max_size_or_value'),
            regex=field_dict.get('regex'),
            regex_description=field_dict.get('regex_description'),
            optional=field_dict.get('optional'),
            default_value=field_dict.get('default_value'),
            allowed_values=field_dict.get('allowed_values'),
            validation_func_name= field_dict.get('validation_func_name'),
        )
        field.group_name = field_dict.get("group_name")
        field._value = field_dict.get("value")
        field.is_validated = field_dict.get("is_validated")
        return field