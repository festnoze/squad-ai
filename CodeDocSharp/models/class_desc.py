from helpers.txt_helper import txt
from models.base_desc import BaseDesc
from models.method_desc import MethodDesc
from models.prop_desc import PropertyDesc
from models.structure_types import StructureType
import json

class ClassDesc(BaseDesc):
    def __init__(self, file_path: str, index_shift_code: int, namespace_name: str, usings: list[str], class_name: str, access_modifier: str, structure_type: str, interfaces_names: list[str] = [], methods: list[MethodDesc] = [], properties: list[PropertyDesc] = []):
        super().__init__(name=class_name)
        self.file_path: str = file_path
        self.index_shift_code: int = index_shift_code
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
    
    def generate_code_from_class_desc(self):
        class_file = ""
        # Using statements
        for using in self.usings:
            class_file += f"using {using};\n"
        class_file += "\n"
        # Namespace and class declaration
        if self.namespace_name:
            class_file += f"namespace {self.namespace_name};\n\n"
        class_file += f"{self.access_modifier} {self.structure_type} {self.class_name}"
        if self.interfaces_names:
            class_file += " : " + ", ".join(self.interfaces_names)
        class_file += "\n"
        # Class content
        class_file += "{\n"
        # Class properties
        for prop in self.properties:
            class_file += txt.indent(1, str(prop) + "\n")
        for method in self.methods:
            class_file += method.to_code(1, True) + "\n"
        return class_file
    
    def generate_code_with_summaries_from_initial_code(self, initial_code: str):
        for method_desc in self.methods[::-1]:
            index = method_desc.code_start_index + self.index_shift_code
            next_nl_dist = initial_code[index:].find('\n')     

            if next_nl_dist != -1:
                next_nl_nindex = index + 2 # add +2 to include the newline+
            else:
                next_nl_nindex = len(initial_code)

            if method_desc.has_attributs():
                att_index = initial_code[:next_nl_nindex].rfind(method_desc.attributs[0])
                att_nl_index = initial_code[:att_index].rfind('\n')
                split_index = att_nl_index + 1 # add +1 to include the newline
            else:
                split_index = next_nl_nindex

            method_summary = '\n' + txt.indent(1, str(method_desc.generated_xml_summary))
            initial_code = initial_code[:split_index] + method_summary + initial_code[split_index:]
        return initial_code

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