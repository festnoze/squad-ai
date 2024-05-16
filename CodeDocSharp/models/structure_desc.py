from typing import List

from pydantic import BaseModel, Field
from helpers.txt_helper import txt
from models.base_desc import BaseDesc
from models.method_desc import MethodDesc, MethodDescPydantic
from models.param_doc import ParameterDocumentation
from models.prop_desc import PropertyDesc, PropertyDescPydantic
from models.structure_types import StructureType
import json

class StructureDesc(BaseDesc):
    def __init__(self, file_path: str, index_shift_code: int, structure_type: StructureType, namespace_name: str, usings: list[str], class_name: str, access_modifier: str, interfaces_names: list[str] = [], methods: list[MethodDesc] = [], properties: list[PropertyDesc] = []):
        super().__init__(name=class_name)
        self.file_path: str = file_path
        self.index_shift_code: int = index_shift_code
        self.structure_type: StructureType = structure_type
        self.namespace_name: str = namespace_name
        self.usings: list[str] = usings
        self.access_modifier: str = access_modifier
        self.class_name: str = class_name
        self.interfaces_names: list[str] = interfaces_names
        self.methods: list[MethodDesc] = methods
        self.properties: list[PropertyDesc] = properties
    
    def __init__(self, **kwargs):
        if len(kwargs) == 1:
            self.params_list: List[ParameterDocumentation] = []
            if 'params_list' in kwargs:      
                for param in kwargs['params_list']:
                    if type(param) is dict:
                        self.params_list.append(ParameterDocumentation(param['param_name'], param['param_desc']))
                    elif type(param) is ParameterDocumentation:
                        self.params_list.append(param)
                    else:
                        raise ValueError('Invalid argument type')
        else:
            for key, value in kwargs.items():
                setattr(self, key, value)
    
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
    
class ClassDescEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, StructureDesc):
            return obj.__dict__
        elif isinstance(obj, MethodDesc):
            return obj.__dict__
        elif isinstance(obj, PropertyDesc):
            return obj.__dict__
        else:
            raise TypeError("Object of type ClassDesc is not an instance and cannot be serialized")

class StructureDescPydantic(BaseModel):
    pass
#     file_path: str = Field(description="Path to the file")
#     index_shift_code: int = Field(description="Index shift code")
#     structure_type: StructureType = Field(description="Type of the structure")
#     namespace_name: str = Field(description="Namespace name")
#     usings: List[str] = Field(description="List of usings")
#     class_name: str = Field(description="Class name")
#     access_modifier: str = Field(description="Access modifier")
#     interfaces_names: List[str] = Field(default_factory=list, description="List of interface names")
#     methods: List[MethodDescPydantic] = Field(default_factory=list, description="List of methods")
#     properties: List[PropertyDescPydantic] = Field(default_factory=list, description="List of properties")
