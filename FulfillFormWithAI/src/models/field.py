from enum import Enum
import re
from typing import Union
from helper import Helper
from models.validation_models import ErrorCode, ValidationError, ValidationResult
from common_tools.helpers.matching_helper import MatchingHelper
from common_tools.helpers.txt_helper import txt

class FieldType(Enum):
    STRING = 'string'
    INTEGER = 'integer'
    FLOAT = 'float'
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
        if new_value is None or new_value == "null": 
            if self.default_value is not None:
                self._value = self.default_value
            else:
                self._value = None
        else:
            self._value = self.normalize_value(new_value)                
        self.perform_validation()
        
    def perform_validation(self):        
        if not self.group:
            self.validation_result = ValidationResult([ValidationError("no_group", "Field is not linked to a group")])
            return
        
        errors: list = []        
        if (self._value is None or self._value == "null") and not self.optional:
            errors.append(ValidationError("value_missing", "Value is required because the field is not flagged as optional"))

        # Validate 'value' for: type, min / max value or size, regex, and allowed values
        if self.value:
            # Check value for type and other constraints
            if self.type == FieldType.STRING:
                if not isinstance(self.value, str):
                    errors.append(ValidationError(ErrorCode.invalid_type, "Expect type to be string"))

            elif self.type == FieldType.INTEGER:
                if not isinstance(self.value, int):
                    errors.append(ValidationError(ErrorCode.invalid_type, "Expect type to be integer"))

            elif self.type == FieldType.FLOAT:
                if not isinstance(self.value, float):
                    errors.append(ValidationError(ErrorCode.invalid_type, "Expect type to be floating point number"))

            elif self.type == FieldType.BOOLEAN:
                if not isinstance(self.value, bool):
                    errors.append(ValidationError(ErrorCode.invalid_type, "Expect type to be boolean"))

            # Check for other constraints only if type is correct
            if any(error.code == ErrorCode.invalid_type for error in errors):
                self.validation_result = ValidationResult(errors)
                self.group.perform_validation()
                return
            
            # Check for min / max size (if string) or value (if number)
            if self.type == FieldType.STRING:
                if self.min_size_or_value and len(self.value) < self.min_size_or_value:
                    errors.append(ValidationError(ErrorCode.min_size_or_value_not_reached, "String length is below the minimum allowed", {"provided_size": len(self.value), "min_size_or_value": self.min_size_or_value}))
                if self.max_size_or_value and len(self.value) > self.max_size_or_value:
                    errors.append(ValidationError(ErrorCode.max_size_or_value_exceeded, "String length exceeds the maximum allowed", {"provided_size": len(self.value), "max_size_or_value": self.max_size_or_value}))
            
            elif self.type == FieldType.INTEGER or self.type == FieldType.FLOAT:
                if self.min_size_or_value and self.value < self.min_size_or_value:
                    errors.append(ValidationError(ErrorCode.min_size_or_value_not_reached, "Value is below the minimum allowed", {"provided_value": self.value, "min_size_or_value": self.min_size_or_value}))
                if self.max_size_or_value and self.value > self.max_size_or_value:
                    errors.append(ValidationError(ErrorCode.max_size_or_value_exceeded, "Value exceeds the maximum allowed", {"provided_value": self.value, "max_size_or_value": self.max_size_or_value}))
        
            # Check for Regex (only for string values)
            if self.type == FieldType.STRING:
                if self.regex and not re.match(self.regex, self.value):
                    errors.append(ValidationError(ErrorCode.regex_no_match, f"Value does not match the following required Regex pattern: {self.regex_description if self.regex_description else self.regex}", {"provided_value": self.value, "regex": self.regex, "regex_description": self.regex_description}))
            
            if self.allowed_values and any(self.allowed_values):
                exact_match_default_value = self.get_default_field_value_exactly_matching_allowed_values(self.value)
                if exact_match_default_value is not None:   
                    if self.value != exact_match_default_value:
                        self.value = exact_match_default_value
                        return
                
                if exact_match_default_value is None:          
                    new_value = self.search_fuzzy_match_within_allowed_values(self.name, self.value, score_min_threshold=0.80)
                    if new_value is not None and new_value != self.value:
                        self.value = new_value
                        return
                    else:
                        errors.append(ValidationError(ErrorCode.no_allowed_values_match, "Value do not belongs to allowed values, neither an approximation of it.", {"provided_value": self.value, "allowed_values": self.allowed_values}))

            # Validate 'value' using the custom validation function
            if self.validation_func_name:
                validation_func = getattr(self.group, self.validation_func_name, None)
                if validation_func and not validation_func(self):
                    errors.append(ValidationError(ErrorCode.custom_validation_fails, f"Custom validation '{self.validation_func_name}' failed"))
        
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
        return f"◦ Field: {self.name}{f" = '{self.value}'" if self.value else ""} <{self.type.value}> with constraints: {constraints_str}."
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self._value,
            "is_valid": self.is_valid,
            "group_name": self.group.name,
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
        field.value = field_dict.get("value")
        return field
        
    def search_fuzzy_match_within_allowed_values(self, field_name: str, field_value: str, score_min_threshold: float = 0.75) -> str | None:
        best_match: str; score: float
        flatten_allowed_values: list[str] = Helper.flatten_inner_lists(self.allowed_values)
        
        if self.get_default_field_value_exactly_matching_allowed_values(field_value):
            raise ValueError(f"Field '{field_name}' with value: '{field_value}' has an exact match in allowed values and shouldn't be looking for fuzzy matching.")
        
        # Search nearest value matching allowed values ...
        best_match, score = MatchingHelper.find_best_approximate_match(flatten_allowed_values, field_value)
        if score >= score_min_threshold:
            txt.print(f"/!\\ Field '{field_name}' with invalid value: '{field_value}' was replaced by the nearest match: '{best_match}' with score: [{score}].")
            # ... then return the default value of the allowed values group containing the best match
            best_match_default_value = self.get_default_field_value_exactly_matching_allowed_values(best_match)
            return best_match_default_value
        
        txt.print(f"/!\\ Field '{field_name}' has an invalid value: '{field_value}'.\nNo close match were found within field's allowed values:\n[{', '.join(flatten_allowed_values)}].\nNearest matching value found is: '{best_match}', with score: {str(score)} - which is less than the specified threshold of {str(score_min_threshold)}.")    
        return None
    
    def get_default_field_value_exactly_matching_allowed_values(self, value: any):
            value_lower = value.strip().lower()
            for allowed_value in self.allowed_values:
                if isinstance(allowed_value, list):
                    for allowed_value_sub_item in allowed_value:
                        if value_lower == allowed_value_sub_item.strip().lower():
                            return allowed_value[0]
                else:
                    if value_lower == allowed_value.strip().lower():
                        return allowed_value
            return None