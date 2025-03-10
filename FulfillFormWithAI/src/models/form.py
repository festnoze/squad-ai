from models.field import Field
from models.group import Group
from models.validation_models import ValidationError, ValidationResult
from common_tools.helpers.file_helper import file

class Form:
    def __init__(self, name: str, groups: list[Group], validation_func: str = None) -> None:
        self.name: str = name
        self.groups: list[Group] = groups
        self.validation_func: any = validation_func

    @staticmethod
    def from_dict(form_dict: dict) -> 'Form':        
        form = Form(
            name=form_dict['form'].get('name'),
            groups= [Group.from_dict(group_data) for group_data in form_dict['form'].get('groups')],
            validation_func=form_dict['form'].get('validation_func')
        )
        return form

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
    
    def get_flatten_fields_values(self) -> dict:
        return {field.name: field.value for group in self.groups for field in group.fields} 

    def to_dict(self) -> dict:
        return {
            'form':{
                'name': self.name,
                'groups': [group.to_dict() for group in self.groups],
                'validation_func': self.validation_func
            }
        }

           
