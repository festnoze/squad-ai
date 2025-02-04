from common_tools.helpers.txt_helper import txt
from models.base_desc import BaseDesc
import json

class PropertyDesc(BaseDesc):
    def __init__(self, prop_name: str, prop_type: str, is_property: bool = False):
        super().__init__(name=prop_name)
        self.prop_name = prop_name
        self.prop_type = prop_type
        self.is_property = is_property
        self.is_field = not is_property

    @staticmethod
    def factory_from_kwargs(**kwargs):
        kwargs = {txt.to_python_case(key): value for key, value in kwargs.items()} # Handle PascalCase names from C#
        prop_name = kwargs.get('prop_name')
        prop_type = kwargs.get('prop_type')
        is_property = kwargs.get('is_property', False)
        return PropertyDesc(prop_name, prop_type, is_property)
        

    def __str__(self):
        str = f"{self.prop_type} {self.prop_name};" 
        if self.is_property:
            str += f" {{ get; set; }}"
        return str

    @staticmethod
    def get_property_desc_from_code(first_line) -> 'PropertyDesc':
        first_line = first_line.replace('const ', '').replace('readonly ', '').strip()
        is_property = first_line.endswith('; }') or first_line.endswith(';}')
        prop_type = first_line.split(' ')[0]
        if is_property:
            prop_name = first_line.split(' ')[1].split('{')[0].strip()
        else:
            prop_name = first_line.split(' ')[1].split(';')[0].strip()
        return PropertyDesc(prop_name, prop_type, is_property)
    
    def to_json(self):
        return json.dumps(self.__dict__, cls=PropDescEncoder)
        
    def to_dict(self):
        return {key: value for key, value in self.__dict__.items()}

class PropertyDescPydantic:
    pass

class PropDescEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, PropertyDesc):
            return obj.__dict__
        return super().default(obj)
