from models.base_desc import BaseDesc
from models.method_desc import MethodDesc
from models.prop_desc import PropertyDesc
from models.structure_types import StructureType
import json

class ClassDesc(BaseDesc):
    def __init__(self, file_path: str, namespace_name: str, usings: list[str], class_name: str, access_modifier: str, structure_type: str, interfaces_names: list[str] = [], methods: list[MethodDesc] = [], properties: list[PropertyDesc] = []):
        super().__init__(name=class_name)
        self.file_path: str = file_path
        self.namespace_name: str = namespace_name
        self.usings: list[str] = usings
        self.access_modifier: str = access_modifier
        self.structure_type: str = structure_type
        self.class_name: str = class_name
        self.interfaces_names: list[str] = interfaces_names
        self.methods: list[MethodDesc] = methods
        self.properties: list[PropertyDesc] = properties
    
    def to_json(self):
        return json.dumps(self.__dict__, cls=ClassDescEncoder, indent=4)
    
    def generate_class_file(self):
        class_file = ""
        for using in self.usings:
            class_file += f"using {using};\n"
        class_file += "\n"
        if self.namespace_name:
            class_file = f"namespace {self.namespace_name};\n\n"
        class_file += f"{self.access_modifier} {self.structure_type} {self.class_name}"
        # if self.base_class_name:
        #     class_file += f" : {self.base_class_name}"
        if self.interfaces_names:
            class_file += " : " + ", ".join(self.interfaces_names)
        class_file += "\n"
        class_file += "{\n"
        for prop in self.properties:
            class_file += f"\t{str(prop)}\n"
        for method in self.methods:
            class_file += f"\t{method.to_str(True)}\n"
        return class_file

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