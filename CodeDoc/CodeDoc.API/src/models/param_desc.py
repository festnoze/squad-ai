import re
from common_tools.helpers.txt_helper import txt
from models.base_desc import BaseDesc
from typing import List, Tuple, Optional
import json

class ParameterDesc(BaseDesc):
    def __init__(self, param_name: str, param_type: str, has_default_value: bool = False, default_value: str = None, description: str = None, extra_infos: str = None):
        super().__init__(name=param_name)
        self.param_name = param_name
        self.param_type = param_type
        self.has_default_value = has_default_value
        self.default_value = default_value
        self.description = description
        self.extra_infos = extra_infos

    @staticmethod
    def factory_from_kwargs(**kwargs) -> 'ParameterDesc':
        kwargs = {txt.to_python_case(key): value for key, value in kwargs.items()} # Handle PascalCase names from C#
        param_name = kwargs.get('param_name')
        param_type = kwargs.get('param_type')
        has_default_value = kwargs.get('has_default_value', False)
        default_value = kwargs.get('default_value')
        description = kwargs.get('description')
        extra_infos = kwargs.get('extra_infos')
        return ParameterDesc(param_name, param_type, has_default_value, default_value, description, extra_infos)

    @staticmethod
    def factory_param_desc_from_code(param_code) -> 'ParameterDesc':
        attributs: Optional[str] = None
        default_value: Optional[str] = None
        has_attributs = False

        param_code = param_code.strip()
        if param_code.startswith('['):
            has_attributs = True
            attributs = param_code[1 : param_code.find(']')].strip()
            param_code = param_code[param_code.find(']') + 1:].strip()
        param_parts = param_code.split(' ')
        param_parts = [part.strip() for part in param_parts if part.strip() != '']
        
        # remove keywords like 'params', 'ref', 'out', 'in' from parameter
        if param_parts[0] == 'params' or param_parts[0] == 'ref' or param_parts[0] == 'out' or param_parts[0] == 'in':
            param_parts = param_parts[1:]

        has_default_value = '=' in param_code

        if has_default_value:
            default_value = param_code.split('=')[1].strip()

        if len(param_parts) != 2 + 2 * has_default_value:
            raise ValueError(f"Invalid parameter code: {param_code}")

        param_type = param_parts[0]
        param_name = param_parts[1].split('=')[0].strip()

        return ParameterDesc(param_name, param_type, has_default_value, default_value, attributs, None)

    def parse_parameter_signature(param: str) -> Tuple[Optional[List[str]], str, str, Optional[str]]:
        # Regular expression to parse the parameter string
        pattern = re.compile(
            r'(?:\[(.*?)\]\s*)?'  # Match attributes, if any
            r'(?P<type>\w+(\<.*?\>)?)\s+'  # Match the type
            r'(?P<name>\w+)'  # Match the name
            r'(?:\s*=\s*(?P<default_value>.+))?'  # Match the default value, if any
        )
        match = pattern.match(param.strip())

        if not match:
            raise ValueError(f"Invalid parameter signature: {param}")

        # Extract the matched groups
        attributs = match.group(1)
        param_type = match.group('type')
        param_name = match.group('name')
        default_value = match.group('default_value')

        # Split attributes if they exist
        if attributs:
            attributs = attributs.split()
        else:
            attributs = None

        return attributs, param_type, param_name, default_value
    
    def to_json(self):
        return json.dumps(self.__dict__, cls=ParamDescEncoder)
    
    def to_dict(self):
        return {key: value for key, value in self.__dict__.items()}
    
    def to_str(self):
        if self.default_value:
            return f"{self.param_type} {self.param_name} = {self.default_value}"
        else:
            return f"{self.param_type} {self.param_name}"

class ParameterDescPydantic:
    pass

class ParamDescEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ParameterDesc):
            return obj.__dict__
        return super().default(obj)
