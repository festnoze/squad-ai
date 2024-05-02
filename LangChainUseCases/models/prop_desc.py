from models.base_desc import BaseDesc
import json

class PropDesc(BaseDesc):
    def __init__(self, prop_name: str, prop_type: str, is_property: bool = False):
        super().__init__(name=prop_name)
        self.prop_name = prop_name
        self.prop_type = prop_type
        self.is_property = is_property
        self.is_field = not is_property
    
    def to_json(self):
        return json.dumps(self.__dict__, cls=PropDescEncoder)

class PropDescEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, PropDesc):
            return obj.__dict__
        return super().default(obj)
