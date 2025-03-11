from models.field import Field
from models.validation_models import ValidationResult, ValidationError

class Group:
    def __init__(self, form, name: str, description: str, fields: list[Field] = [], validation_func: str = None) -> None:
        self.form = form
        self.name: str = name
        self.description: str = description
        self.validation_func: any = validation_func
        self.fields: list[Field] = fields        
        self.validation_result: ValidationResult = ValidationResult([ValidationError('no_validation','no validation has been done yet')])
        for field in self.fields:
            field.group = self
    
    @property
    def is_valid(self) -> bool:
        return self.validation_result.is_valid

    def perform_validation(self):
        if not self.form:
            self.validation_result = ValidationResult([ValidationError("no_form", "Group is not linked to a form")])
            return
        
        errors: list = []
        # Validate group using custom validation function
        if self.validation_func:
            group_validation = getattr(self, self.validation_func, None)
            if group_validation and not group_validation():
                errors.append(ValidationError("group_custom", f"Custom group validation '{self.validation_func}' failed"))
        
        # Get validation errors from each fields of the group
        for field in self.fields:            
            if not field.is_valid:
                for err in field.validation_result.errors:
                    errors.append(ValidationError(err.code, f"In field '{field.name}', {err.message}", err.details))
        
        self.validation_result = ValidationResult(errors)
        self.form.perform_validation()
    
    def set_values(self, values: list) -> None:
        if len(values) != len(self.fields):
            raise ValueError("Values list must have the same length as the fields list")
        for i in range(len(self.fields)):
            self.fields[i].value = values[i]

    def __str__(self) -> str:
        fields_str: str = "\n    " + "\n    ".join(str(field) for field in self.fields)
        return f"  • Group: '{self.name}' ({self.description}).{fields_str}"
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'description': self.description,
            'fields': [field.to_dict() for field in self.fields],
            'validation_func': self.validation_func
        }
    
    @staticmethod
    def from_dict(group_dict: dict) -> 'Group':
        group = Group(
            form=None,
            name=group_dict.get('name'),
            description=group_dict.get('description'),
            fields= [Field.from_dict(field_data) for field_data in group_dict['fields']],
            validation_func=group_dict.get('validation_func'),
        )
        return group
