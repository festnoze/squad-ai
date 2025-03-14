from models.group import Group
from models.validation_models import ValidationError, ValidationResult

class Form:
    def __init__(self, name: str, groups: list[Group] = [], validation_func: str = None) -> None:
        self.name: str = name
        self.groups: list[Group] = groups
        self.validation_func: any = validation_func
        self.validation_result: ValidationResult = ValidationResult([ValidationError('no_validation','no validation has been done yet')])
        for group in self.groups:
            group.form = self
    
    @property
    def is_valid(self) -> bool:
        return self.validation_result.is_valid

    @staticmethod
    def from_dict(form_dict: dict) -> 'Form':        
        form: Form = Form(
            name=form_dict['form'].get('name'),
            groups = [Group.from_dict(group_data) for group_data in form_dict['form'].get('groups')],
            validation_func=form_dict['form'].get('validation_func')
        )
        form.perform_full_validation()
        return form

    def perform_validation(self):
        errors: list = []
        # Validate form using its custom validation function
        if self.validation_func:
                form_validation = getattr(self, self.validation_func, None)
                if form_validation and not form_validation(self):
                        errors.append(ValidationError("form_custom", f"Custom form validation '{self.validation_func}' failed"))
        
        # Get validation errors from each group of the form
        for group in self.groups:
            if not group.is_valid:
                for err in group.validation_result.errors:
                    errors.append(ValidationError(err.code, f"In group '{group.name}', {err.message}", err.details))

        self.validation_result = ValidationResult(errors)

    def perform_full_validation(self):
        for group in self.groups:
            for field in group.fields:
                field.perform_validation()

    def __str__(self) -> str:
        groups_str: str = "\n\n".join(str(group) for group in self.groups)
        return f"Form name: '{self.name}'.\n\n{groups_str}"
    
    def get_all_fields_values(self) -> dict:
        return {field.name: field.value for group in self.groups for field in group.fields} 

    def to_dict(self) -> dict:
        return {
            'form':{
                'name': self.name,
                'groups': [group.to_dict() for group in self.groups],
                'validation_func': self.validation_func
            }
        }

           
