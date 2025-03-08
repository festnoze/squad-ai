from models.field import Field
from models.validation_models import ValidationResult, ValidationError

class Group:
    def __init__(self, name: str, description: str, fields: list[Field], validation_func: str = None) -> None:
        self.name: str = name
        self.description: str = description
        self.validation_func: any = validation_func
        self.fields: list[Field] = fields
        for field in self.fields:
            field.group_name = self.name

    def validate(self) -> ValidationResult:
        errors: list = []
        for field in self.fields:
            if field.validation_func_name:
                validation_func = getattr(self, field.validation_func_name, None)
                if validation_func and not validation_func():
                    errors.append(ValidationError("group_field_custom", f"Custom validation '{field.validation_func_name}' failed in field '{field.name}'"))
            field_result: ValidationResult = field.validate()
            if not field_result.is_valid:
                for err in field_result.errors:
                    errors.append(ValidationError(err.code, f"In field '{field.name}': {err.message}", err.details))
        if self.validation_func:
            group_validation = getattr(self, self.validation_func, None)
            if group_validation and not group_validation():
                errors.append(ValidationError("group_custom", f"Custom group validation '{self.validation_func}' failed"))
        return ValidationResult(len(errors) == 0, errors)
    
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
        return Group(
            name=group_dict.get('name'),
            description=group_dict.get('description'),
            fields= [Field.from_dict(field_data) for field_data in group_dict['fields']],
            validation_func=group_dict.get('validation_func')
        )
