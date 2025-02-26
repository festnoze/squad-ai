class ValidationError:
    def __init__(self, code: str, message: str, details: dict = None) -> None:
         self.code: str = code
         self.message: str = message
         self.details: dict = details if details is not None else {}

class ValidationResult:
    def __init__(self, is_valid: bool, errors: list) -> None:
         self.is_valid: bool = is_valid
         self.errors: list = errors