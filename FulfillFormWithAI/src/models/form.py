from models.group import Group
from models.validation_models import ValidationError, ValidationResult
from common_tools.helpers.file_helper import file

class Form:
    def __init__(self, name: str, groups: list[Group], validation_func: str = None) -> None:
        self.name: str = name
        self.groups: list[Group] = groups
        self.validation_func: any = validation_func

    def validate(self) -> ValidationResult:
        errors: list = []
        for group in self.groups:
                group_result: ValidationResult = group.validate()
                if not group_result.is_valid:
                        errors.extend(group_result.errors)
        if self.validation_func:
                form_validation = getattr(self, self.validation_func, None)
                if form_validation and not form_validation(self):
                        errors.append(ValidationError("form_custom", f"Custom form validation '{self.validation_func}' failed"))
        return ValidationResult(len(errors) == 0, errors)

    def __str__(self) -> str:
        groups_str: str = "\n\n".join(str(group) for group in self.groups)
        return f"Form name: '{self.name}'.\n\n{groups_str}"
    
    def to_flatten_fields(self) -> dict:
        return {field.name: field.value for group in self.groups for field in group.fields} 

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'groups': [group.to_dict() for group in self.groups],
            'validation_func': self.validation_func
        }

           
