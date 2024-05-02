from models.base_desc import BaseDesc
from models.method_desc import MethodDesc
from models.prop_desc import PropertyDesc
import json

class ClassDesc(BaseDesc):
    def __init__(self, file_path: str, class_name: str, interfaces_names: list[str] = [], methods: list[MethodDesc] = [], properties: list[PropertyDesc] = []):
        super().__init__(name=class_name)
        self.file_path = file_path
        self.class_name = class_name
        self.interfaces_names = interfaces_names
        self.methods = methods
        self.properties = properties
    
    def to_json(self):
        return json.dumps(self.__dict__, cls=ClassDescEncoder, indent=4)

class ClassDescEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ClassDesc):
            return obj.__dict__
        elif isinstance(obj, MethodDesc):
            return obj.__dict__
        elif isinstance(obj, PropertyDesc):
            return obj.__dict__
        else:
            raise TypeError("Object of type ClassDesc is not an instance and cannot be serialized")
    
class InterfaceDesc(BaseDesc):
    def __init__(self, file_path: str, interface_name: str, base_interfaces_names: list[str] = [], methods: list[MethodDesc] = [], properties: list[PropertyDesc] = []):
        super().__init__(name=interface_name)
        self.file_path = file_path
        self.interface_name = interface_name
        self.base_interfaces_names = base_interfaces_names
        self.methods = methods
        self.properties = properties
    
    def to_json(self):
        return json.dumps(self.__dict__)