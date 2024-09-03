from typing import List

from pydantic import BaseModel, Field
from helpers.txt_helper import txt
from models.base_desc import BaseDesc
from models.enum_desc import EnumMembersDesc
from models.method_desc import MethodDesc, MethodDescPydantic
from models.param_desc import ParameterDesc
from models.param_doc import ParameterDocumentation
from models.prop_desc import PropertyDesc, PropertyDescPydantic
from models.structure_types import StructureType
import json

class StructureDesc(BaseDesc):
    #def __init__(self, file_path: str, index_shift_code: int, indent_level: int, struct_type: StructureType, namespace_name: str, usings: list[str], struct_name: str, access_modifier: str, base_class_name: str, interfaces_names: list[str] = [], existingSummary = '', attributs = None, methods: list[MethodDesc] = [], properties: list[PropertyDesc] = []):
    def __init__(
        self, 
        file_path: str, 
        index_shift_code: int,
        indent_level: int,
        struct_type: StructureType, 
        namespace_name: str, 
        usings: List[str], 
        struct_name: str, 
        access_modifier: str, 
        base_class_name: str, 
        interfaces_names: List[str] = None,
        existing_summary: str = "",
        attributs: List[str] = None,
        methods: List[MethodDesc] = None, 
        properties: List[PropertyDesc] = None,
        enum_members: EnumMembersDesc = None,
        generated_summary: str = None
    ):
        super().__init__(name=struct_name)
        self.file_path: str = file_path
        self.index_shift_code: int = index_shift_code
        self.indent_level: int = indent_level
        self.struct_type: StructureType = struct_type
        self.namespace_name: str = namespace_name
        self.usings: list[str] = usings
        self.access_modifier: str = access_modifier
        self.struct_name: str = struct_name
        self.base_class_name: str = base_class_name
        self.interfaces_names: list[str] = interfaces_names
        self.existing_summary: str = existing_summary
        self.attributs: List[str] = attributs if attributs is not None else []
        self.related_structures: list[StructureDesc] = []
        self.methods: list[MethodDesc] = methods
        self.properties: list[PropertyDesc] = properties,
        self.enum_members: EnumMembersDesc = enum_members,
        self.generated_summary: str = generated_summary
    
    def __init__(self, **kwargs):
        if len(kwargs) == 1 and 'params_list' in kwargs:
            self.params_list: List[ParameterDocumentation] = []
            for param in kwargs['params_list']:
                if type(param) is dict:
                    self.params_list.append(ParameterDocumentation(param['param_name'], param['param_desc']))
                elif type(param) is ParameterDocumentation:
                    self.params_list.append(param)
                else:
                    raise ValueError('Invalid argument type')
        else:
            for key, value in kwargs.items():
                key = txt.to_python_case(key)
                if key == 'struct_type':
                    if type(value) is int:
                        self.struct_type: str = StructureType(value)
                    else:
                        self.struct_type: str = StructureType[value]
                elif key == 'methods':
                    if type(value) is list and len(value) > 0 and type(value[0]) is MethodDesc:
                        self.methods: list[MethodDesc] = value
                    else:
                        self.methods: list[MethodDesc] = [MethodDesc.factory_from_kwargs(**method) for method in value]                    
                elif key == 'properties':
                    if type(value) is list and len(value) > 0 and type(value[0]) is PropertyDesc:
                        self.properties: list[PropertyDesc] = value
                    else:
                         self.properties: list[PropertyDesc] = [PropertyDesc.factory_from_kwargs(**prop) for prop in value]
                elif key == 'enum_members':
                    if type(value) is EnumMembersDesc:
                        self.enum_members: EnumMembersDesc = value
                    else:
                        self.enum_members: EnumMembersDesc = EnumMembersDesc.factory_from_kwargs(**value)
                else:
                    setattr(self, key, value)
    
    def to_json(self):
        return json.dumps(self.__dict__, cls=StructureDescEncoder, indent=4)
    
    def to_dict(self):
        result = {key: value for key, value in self.__dict__.items() if key not in ['struct_type', 'methods', 'properties']}
        result['struct_type'] = str(self.struct_type)
        result['methods'] = [method.to_dict() for method in self.methods]
        result['properties'] = [prop.to_dict() for prop in self.properties]
        return result
    
    def __repr__(self):
        return f"StructureDesc(name={self.name}, type={self.struct_type.name})"
    
    def __str__(self):
        return f"StructureDesc(name={self.name}, type={self.struct_type.name})"
    
    def generate_code_from_class_desc(self):
        class_file = ""
        # Using statements
        for using in self.usings:
            class_file += f"using {using};\n"
        class_file += "\n"
        # Namespace and class declaration
        if self.namespace_name:
            class_file += f"namespace {self.namespace_name};\n\n"
        class_file += f"{self.access_modifier} {self.struct_type} {self.struct_name}"
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
    
class StructureDescEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, StructureType):
            return obj.name
        else:
            return obj.__dict__

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
