from models.base_desc import BaseDesc
import json

class ParameterDesc(BaseDesc):
    def __init__(self, param_name: str, param_type: str, has_default_value: bool = False, default_value: str = None, description: str = None, extra_infos: str = None):
        super().__init__(name=param_name)
        self.param_name = param_name
        self.param_type = param_type
        self.default_value = default_value
        self.description = description
        self.extra_infos = extra_infos

    @staticmethod
    def factory_param_desc_from_code(param_code) -> 'ParameterDesc':
        extra_infos: str = None
        if '[' and ']' in param_code:
            extra_infos = param_code[param_code.index('[')+1: param_code.rindex(']')].strip()
            param_code = param_code.replace(f"[{extra_infos}]", "").strip()
        param_type = param_code.split(' ')[0]
        param_name = param_code.split(' ')[1].split('=')[0].strip()
        has_default_value = '=' in param_code
        default_value = param_code.split('=')[1].strip() if has_default_value else None
        return ParameterDesc(param_name, param_type, has_default_value, default_value, extra_infos)
    
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
