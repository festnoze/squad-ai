from models.field import Field, FieldType
from models.form import Form
from models.group import Group
#
from common_tools.helpers.file_helper import file

class FormService:
    @staticmethod
    def create_form_from_yaml_file(file_path: str) -> Form:
        yaml_data = file.get_as_yaml(file_path)
        return FormService.create_form_from_yaml(yaml_data)
    
    @staticmethod
    def create_form_from_yaml(yaml_data: dict) -> Form:
        groups = []
        for group_data in yaml_data['form']['groups']:
            fields = []
            for field_data in group_data['fields']:
                field = Field(
                    name=field_data['name'],
                    description=field_data['description'],
                    type=field_data['type'],
                    min_size_or_value=field_data.get('min_size_or_value'),
                    max_size_or_value=field_data.get('max_size_or_value'),
                    regex=field_data.get('regex'),
                    optional=field_data.get('optional'),
                    default_value=field_data.get('default_value'),
                    allowed_values=field_data.get('allowed_values'),
                    validation_func_name= field_data.get('validation_func_name'),
                )
                fields.append(field)
            group = Group(
                name=group_data['name'],
                description=group_data['description'],
                fields=fields
            )
            groups.append(group)
        
        form = Form(
            name=yaml_data['form']['name'],
            groups=groups
        )
        return form

# Exemple d'utilisation :
# yaml_data = yaml.safe_load(open('formulaire.yaml'))
# form = create_form_from_yaml(yaml_data)
