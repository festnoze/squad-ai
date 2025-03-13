import asyncio
from enum import Enum
import re
from typing import Union
from helper import Helper
from models.validation_models import ValidationError, ValidationResult
from common_tools.helpers.rag_bm25_retriever_helper import BM25RetrieverHelper
from common_tools.helpers.txt_helper import txt

class FieldType(Enum):
    INTEGER = 'integer'
    STRING = 'string'
    DECIMAL = 'decimal'
    DATE = 'date'
    DATETIME = 'datetime'
    BOOLEAN = 'boolean'
    FILE = 'file'

class Field:
    def __init__(self, group, name: str, description: str, type: str, min_size_or_value: any = None, max_size_or_value: any = None, regex: str = None,
            regex_description: str = None, optional: bool = False, default_value: str = None, allowed_values: list[str] = None, validation_func_name: str = None) -> None:      
        self.group = group
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
        self.validation_result: ValidationResult = ValidationResult([ValidationError('not_validate','no validation has been performed yet')])
        self._value: any = None
    
    @property
    def is_valid(self) -> bool:
        return self.validation_result.is_valid
    
    @property
    def value(self) -> any:
        return self._value

    @value.setter
    def value(self, new_value: any) -> None:
        if (new_value is None or new_value == "null"):
            if not self.optional: 
                raise ValueError("Value is required because the field is flagged as not-optional")
            self._value = None
        else:
            self._value = self.normalize_value(new_value)        
        self.perform_validation()
        
    def perform_validation(self):        
        if not self.group:
            self.validation_result = ValidationResult([ValidationError("no_group", "Field is not linked to a group")])
            return
        
        errors: list = []        
        if not self.value and not self.optional:
            errors.append(ValidationError("value_missing", "Value is required"))

        # Validate 'value' for: type, min/max value or size, regex, and allowed values
        if self.value:
            # Check for type and constraints
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

            
            flatten_allowed_values = Helper.flatten_inner_lists(self.allowed_values)

            # Check if value belongs to the allowed ones
            if self.allowed_values and any(self.allowed_values):
                # Check if the value is an exact match within the allowed values
                if self.value in flatten_allowed_values:   
                    # check if the value is the default value for this allowed values group (the 1st item of the sub-list), ...
                    # if not, replace the actual value by the corresponding default value of this group.
                    exact_match_default_value = Field.get_default_field_value_exactly_matching_allowed_values_async(self.value, self.allowed_values)
                    if exact_match_default_value and self.value != exact_match_default_value:
                        self.value = exact_match_default_value
                        return
                
                # If the value is invalid value, search within allowed values for a fuzzy matching value
                if self.value not in flatten_allowed_values:                
                    new_value = Field.get_field_value_fuzzy_matching_allowed_values(self.name, self.value, flatten_allowed_values)
                    if new_value is not None and new_value != self.value:
                        self.value = new_value
                        return
                    errors.append(ValidationError("invalid_value", "Value do not belongs to allowed values", {"provided_value": self.value, "allowed_values": self.allowed_values}))

            # Validate 'value' using the custom validation function
            if self.validation_func_name:
                validation_func = getattr(self.group, self.validation_func_name, None)
                if validation_func and not validation_func(self):
                    errors.append(ValidationError("custom_validation", f"Custom validation '{self.validation_func_name}' failed"))
        
        self.validation_result = ValidationResult(errors)
        self.group.perform_validation()
    
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
            constraints.append(f"allowed_values={', '.join(Helper.flatten_inner_lists(self.allowed_values))}")
        constraints_str: str = f"{', '.join(constraints)}" if constraints else ""
        return f"◦ Field: {self.name} <{self.type.value}>{f" = '{self.value}'" if self.value else ""} with constraints: {constraints_str}."
    
    def to_dict(self) -> dict:
        return {
            "group_name": self.group.name,
            "name": self.name,
            "description": self.description,
            "optional": self.optional,
            "type": self.type.value,
            "regex": self.regex,
            "regex_description": self.regex_description,
            "min_size_or_value": self.min_size_or_value,
            "max_size_or_value": self.max_size_or_value,
            "validation_func_name": self.validation_func_name,
            "default_value": self.default_value,
            "allowed_values": self.allowed_values,
            "value": self._value,
            "is_valid": self.is_valid,
        }
    
    @staticmethod
    def from_dict(field_dict: dict) -> 'Field':
        field = Field(
            group=None,
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

        field._value = field_dict.get("value")
        return field
        
    def get_field_value_fuzzy_matching_allowed_values(field_name: str, field_value: str, flatten_allowed_values: list[str], score_min_threshold: float = 0.5) -> str | None:
        # Search exact value matching allowed values (case insensitive + get default value if sub-lists)
        if Field.get_default_field_value_exactly_matching_allowed_values_async(field_value, flatten_allowed_values):
            raise ValueError(f"Field '{field_name}' with value: '{field_value}' has an exact match in allowed values and shouldn't be looking for fuzzy matching.")
        
        # Search nearest value matching allowed values
        best_match: str; score: float
        best_match, score = BM25RetrieverHelper.find_best_match_bm25(flatten_allowed_values, field_value)
        if score > score_min_threshold:
            txt.print(f"/!\\ Field '{field_name}' with invalid value: '{field_value}' was replaced by the nearest match: '{best_match}' with score: [{score}].")
            return Field.get_default_field_value_exactly_matching_allowed_values_async(best_match, flatten_allowed_values)

        txt.print(f"/!\\ Field '{field_name}' has an invalid value: '{field_value}'.\nNo close match were found within field's allowed values:\n[{', '.join(flatten_allowed_values)}].\nNearest matching value found is: '{best_match}', with score: {str(score)} - which is less than the specified threshold of {str(score_min_threshold)}.")    
        return None
    
    def get_default_field_value_exactly_matching_allowed_values_async(value: any, allowed_values:list):
            value_lower = value.strip().lower()
            for allowed_value in allowed_values:
                if isinstance(allowed_value, list):
                    for allowed_value_sub_item in allowed_value:
                        if value_lower == allowed_value_sub_item.strip().lower():
                            return allowed_value[0]
                else:
                    if value_lower == allowed_value.strip().lower():
                        return allowed_value
            return None