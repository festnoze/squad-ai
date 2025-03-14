from enum import Enum

class ErrorCode(Enum):
    invalid_type = "invalid_type"
    min_size_or_value_not_reached = "min_size_or_value_not_reached"
    max_size_or_value_exceeded = "max_size_or_value_exceeded"
    regex_no_match = "regex_no_match"
    no_allowed_values_match = "no_allowed_values_match"
    custom_validation_fails = "custom_validation_fails"

class ValidationError:
    def __init__(self, code: ErrorCode, message: str, details: dict = None) -> None:
         self.code: ErrorCode = code
         self.message: str = message
         self.details: dict = details if details is not None else {}

class ValidationResult:
    def __init__(self, errors: list[ValidationError]) -> None:
         self.is_valid: bool = not any(errors)
         self.errors: list[ValidationError] = errors
