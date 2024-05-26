from helpers.txt_helper import txt
from models.base_desc import BaseDesc
import json
import re

from models.param_desc import ParameterDesc
from models.params_doc import MethodParametersDocumentation

class MethodDesc(BaseDesc):
    def __init__(self, code_start_index: int, existing_summary: str, attributs: list[str], method_name: str, method_return_type: str, method_params: list[ParameterDesc], indent_level: int, code: str, is_async: bool = False, is_task: bool = False, is_ctor: bool = False, is_static: bool = False, is_abstract: bool = False, is_override: bool = False, is_virtual: bool = False, is_sealed: bool = False, is_new: bool = False):
        super().__init__(name=method_name)
        self.code_start_index: int = code_start_index
        self.method_name: str = method_name
        self.existing_summary: str = existing_summary
        self.attributes: list[str] = attributs
        self.return_type: str = method_return_type
        self.params: list[ParameterDesc] = method_params
        self.indent_level: int = indent_level
        self.code: str = code
        self.is_async: bool = is_async
        self.is_task: bool = is_task
        self.is_ctor: bool = is_ctor
        self.is_static: bool = is_static
        self.is_abstract: bool = is_abstract
        self.is_override: bool = is_override
        self.is_virtual: bool = is_virtual
        self.is_sealed: bool = is_sealed
        self.is_new: bool = is_new

        self._code_chunks: list[str] = None
        @property
        def code_chunks(self):
            if not self._code_chunks:
                return [self.code]
            return self._code_chunks
        
        self.generated_summary: str = None
        self.generated_parameters_summaries: MethodParametersDocumentation = None
        self.generated_return_summary: str = None
        self.generated_xml_summary: str = None

    @staticmethod
    def factory_from_kwargs(**kwargs):
        kwargs = {txt.to_python_case(key): value for key, value in kwargs.items()} # Handle PascalCase names from C#
        code_start_index = kwargs.get('code_start_index')
        existing_summary = kwargs.get('existing_summary')
        attributs = kwargs.get('attributs')
        method_name = kwargs.get('method_name')
        method_return_type = kwargs.get('method_return_type')
        params = kwargs.get('params')
        params = [ParameterDesc.factory_from_kwargs(**param) for param in params]
        indent_level = kwargs.get('indent_level')
        code = kwargs.get('code')
        is_async = kwargs.get('is_async', False)
        is_task = kwargs.get('is_task', False)
        is_ctor = kwargs.get('is_ctor', False)
        is_static = kwargs.get('is_static', False)
        is_abstract = kwargs.get('is_abstract', False)
        is_override = kwargs.get('is_override', False)
        is_virtual = kwargs.get('is_virtual', False)
        is_sealed = kwargs.get('is_sealed', False)
        is_new = kwargs.get('is_new', False)
        return MethodDesc(code_start_index, existing_summary, attributs, method_name, method_return_type, params, indent_level, code, is_async, is_task, is_ctor, is_static, is_abstract, is_override, is_virtual, is_sealed, is_new)

    def to_code(self, indent_level: int = 1, include_summary: bool = False):
        method_code: str = ""
        # Add summary (generated or existing)
        if include_summary:
            if self.generated_xml_summary:
                method_code += txt.indent(indent_level, f"{self.generated_xml_summary}\n")
            else:
                method_code +=  txt.indent(indent_level, f"{self.summary}\n")
        # Add method full signature
        method_code += txt.indent(indent_level, f"{self.return_type} {self.method_name}({', '.join([str(param) for param in self.params])})\n")
        # Add method code
        method_code += txt.indent(indent_level, "{\n")
        indent_level += 1
        method_code += txt.indent(indent_level, self.code)
        indent_level -= 1
        method_code += txt.indent(indent_level, "}\n\n")
        return method_code
    
    @staticmethod
    def factory_for_method_from_class_code(code: str, start_index: int, previous_chunk:str, class_name: str) -> 'MethodDesc':
        #retrieve summary and attributs from previous chunk
        previous_chunk_last_double_newline_index = previous_chunk.rfind('\n\n')
        previous_chunk_last_brace_index = previous_chunk.rfind('}')
        summary_lines: list[str] = []
        attributs: list[str] = []
        if previous_chunk_last_double_newline_index > previous_chunk_last_brace_index:
            previous_chunk_last_part = previous_chunk[previous_chunk_last_double_newline_index:]
            attributs = MethodDesc.detect_attributs(previous_chunk_last_part)
            summary_lines = [line.strip()for line in previous_chunk_last_part.split('\n') if '///' in line]
        
        # get method infos from main code chunk
        method_sign = code.split('{')[0].strip()
        is_ctor = class_name == method_sign.split('(')[0].strip()
        is_task = 'Task<' in method_sign
        is_async = 'async ' in method_sign
        is_override = 'override ' in method_sign
        is_new = 'new ' in method_sign
        is_static = 'static ' in method_sign
        is_abstract = 'abstract ' in method_sign
        is_virtual = 'virtual ' in method_sign
        is_sealed = 'sealed ' in method_sign

        if not is_ctor:
            if is_async or is_override or is_new or is_static or is_abstract or is_virtual or is_sealed:
                method_sign = method_sign.replace('override ', '').replace('new ', '').replace('async ','').replace('static ','').replace('abstract ','').replace('virtual ','').replace('sealed ','').strip() 

            if is_async:
                method_return_type = method_sign.split(' ')[0].replace('Task<', '').rsplit('>', 1)[0]
            else:
                method_return_type = method_sign.split(' ')[0]
            method_name = method_sign.split(' ')[1].split('(')[0]

        if is_ctor:
            method_name = class_name
            method_return_type = None

        method_params = MethodDesc.get_method_parameters(method_sign)
        method_code = code
        if '{' and '}' in method_code: # remove method main brackets {}
            method_code = code.split('{')[1].rsplit('}', 1)[0].strip()
        if '{' and '}' in method_code: # write others brackets {} as litteral (no to be confond with formating brackets)
            method_code = method_code.replace('{', '{{}').replace('}', '}}')
        return MethodDesc(start_index, '\n'.join(summary_lines), attributs, method_name, method_return_type, method_params, 1, method_code, is_async, is_task, is_ctor, is_static, is_abstract, is_override, is_virtual, is_sealed, is_new)
    
    def factory_for_interface_code(code: str, start_index: int, interface_name: str) -> 'MethodDesc':
        summary_lines: list[str] = []
        attributs: list[str] = []
        # if previous_chunk_last_double_newline_index > previous_chunk_last_brace_index:
        #     previous_chunk_last_part = previous_chunk[previous_chunk_last_double_newline_index:]
        #     attributs = MethodDesc.detect_attributes(previous_chunk_last_part)
        #     summary_lines = [line.strip() for line in previous_chunk_last_part.split('\n') if '///' in line]
        
        # get method infos from main code chunk
        method_sign = code.split(')')[0] + ')'
        is_ctor = False
        is_task = 'Task<' in method_sign
        is_async = False
        is_override = 'override ' in method_sign
        is_new = 'new ' in method_sign
        is_static = 'static ' in method_sign
        is_abstract = 'abstract ' in method_sign
        is_virtual = 'virtual ' in method_sign
        is_sealed = 'sealed ' in method_sign

        if not is_ctor:
            if is_async or is_override or is_new or is_static or is_abstract or is_virtual or is_sealed:
                method_sign = method_sign.replace('override ', '').replace('new ', '').replace('async ','').replace('static ','').replace('abstract ','').replace('virtual ','').replace('sealed ','').strip() 

            if is_task:
                method_return_type = method_sign.split(' ')[0].replace('Task<', '').rsplit('>', 1)[0]
            else:
                method_return_type = method_sign.split(' ')[0]
            method_name = method_sign.split(' ')[1].split('(')[0]

        method_params = MethodDesc.get_method_parameters(method_sign)
        if '{' and '}' in code:
            method_code = code.split('{')[1].rsplit('}', 1)[0].strip()
        else:
            method_code = ''

        return MethodDesc(start_index, '\n'.join(summary_lines), attributs, method_name, method_return_type, method_params, 1, method_code, is_async, is_task, is_ctor, is_static, is_abstract, is_override, is_virtual, is_sealed, is_new)
    
    def has_return_type(self) -> bool:
        return self.return_type is not None and self.return_type != 'void' and self.return_type != 'Task' and not self.is_ctor
    
    @staticmethod
    def get_method_parameters(method_sign: str) -> list[ParameterDesc]:
        params_start_index = method_sign.index('(') + 1
        params_end_index = method_sign.rindex(')')
        params_str = method_sign[params_start_index:params_end_index]
        params = [param.strip() for param in params_str.split(',') if param.strip()]
        params_desc = [ParameterDesc.factory_param_desc_from_code(param) for param in params]
        return params_desc

    @staticmethod
    def detect_attributs(code: str) -> list[str]:
        attributs_list: list[str] = []
        attribute_pattern = r'\[.*?\]'
        lines = code.split('\n')
        for line in lines:
            if '[' in line:
                line_attributes = re.findall(attribute_pattern, line)
                if len(line_attributes) > 0:
                    attributs_list.extend(line_attributes)
        return attributs_list
    
    def to_json(self):
        return json.dumps(self.__dict__, cls=MethodDescEncoder)

class MethodDescPydantic:
    pass

class MethodDescEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, MethodDesc):
            return obj.__dict__
        return super().default(obj)
