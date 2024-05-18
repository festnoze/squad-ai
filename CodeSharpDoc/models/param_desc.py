from models.base_desc import BaseDesc
import json

class ParameterDesc(BaseDesc):
    def __init__(self, param_name: str, param_type: str, has_default_value: bool = False, default_value: str = None, description: str = None):
        super().__init__(name=param_name)
        self.param_name = param_name
        self.param_type = param_type
        self.default_value = default_value
        self.description = None

    @staticmethod
    def get_param_desc_from_code(code) -> 'ParameterDesc':
        param_type = code.split(' ')[0]
        param_name = code.split(' ')[1].split('=')[0].strip()
        has_default_value = '=' in code
        default_value = code.split('=')[1].strip() if has_default_value else None
        return ParameterDesc(param_name, param_type, has_default_value, default_value)
    
    def to_json(self):
        return json.dumps(self.__dict__, cls=ParamDescEncoder)
    
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
