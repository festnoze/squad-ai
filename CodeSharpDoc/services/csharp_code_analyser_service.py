from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
import re
# internal imports
from helpers.txt_helper import txt
from models.base_desc import BaseDesc
from models.structure_desc import StructureDesc, StructureDescPydantic
from models.method_desc import MethodDesc
from models.param_doc import ParameterDocumentation
from models.params_doc import MethodParametersDocumentation, MethodParametersDocumentationPydantic
from models.prop_desc import PropertyDesc
from models.structure_types import StructureType
from summarize import Summarize
import re

class CSharpCodeStructureAnalyser:
    @staticmethod
    def extract_code_structures_from_code_files(llm, paths_and_codes):
        all_parsed_structs = []
        for file_path, code in paths_and_codes.items():
            structure_description: StructureDesc = CSharpCodeStructureAnalyser.get_code_structure(llm, file_path, code)
            all_parsed_structs.append(structure_description)
        return all_parsed_structs
    
    @staticmethod
    def get_code_structure(llm: BaseChatModel, file_path: str, code: str, chunk_size:int = 8000, chunk_overlap: int = 0) -> BaseDesc:
        found_struct_separators, separator_indexes, splitted_struct_contents = CSharpCodeStructureAnalyser.split_by_class_interface_enum_definition(code)
        
        # TODO: don't yet handle files with multiple class/interface/enum definitions (can happened, especially in transfert objects files)
        if len(splitted_struct_contents) > 2:
            raise Exception('Multiple class/interface/enum definitions per file are not yet supported')
        
        first_chunk_has_usings = 'using' in splitted_struct_contents[0]
        first_chunk_has_namespace = 'namespace' in splitted_struct_contents[0]
        access_modifier = found_struct_separators[-1].split()[0]
        struct_type: str = found_struct_separators[-1].split()[-1]

        if first_chunk_has_namespace:
            namespace_name = re.search(r'namespace\s+([\w.]+)[\s;]*', splitted_struct_contents[0]).group(1)
        if first_chunk_has_usings:
            usings = re.findall(r'using\s+([\w.]+)[\s;]*', splitted_struct_contents[0]) 

        if struct_type == StructureType.Class.value:
            struct_desc = CSharpCodeStructureAnalyser.class_extract_methods_and_props(file_path, separator_indexes[0], namespace_name, usings, access_modifier, splitted_struct_contents[-1])
            # split each method into chunks adapted to the LLM context window size
            CSharpCodeStructureAnalyser.split_class_methods_and_add_to_class_desc(struct_desc, chunk_size, chunk_overlap)
        elif struct_type == StructureType.Interface.value:
            struct_desc = CSharpCodeStructureAnalyser.interface_extract_methods_and_props(llm, file_path, separator_indexes[0], namespace_name, usings, access_modifier, splitted_struct_contents[-1])
        elif struct_type == StructureType.Enum.value:
            pass
        return struct_desc
    
    def split_class_methods_and_add_to_class_desc(class_desc: StructureDesc, chunk_size:int = 8000, chunk_overlap: int = 0):
        # split each method into chunks adapted to the LLM context window size
        chunk_count = 0
        for method in class_desc.methods:
            method_chunks = CSharpCodeStructureAnalyser.split_method(method.code, chunk_size, chunk_overlap)
            if (len(method_chunks) < 2):
                method.code_chunks = None
            else:
                method.code_chunks = method_chunks
            chunk_count += len(method_chunks)

    def split_by_class_interface_enum_definition(code: str) -> tuple[list[str], list[str], list[int]]:
        struct_separators_array = [
            'public class ', 'protected class ', 'private class ', 'internal class ', 
            'public interface ', 'protected interface ', 'private interface ', 'internal interface' , 
            'public enum ', 'protected enum ', 'private enum ', 'internal enum '
            ]
        struct_separators = '|'.join(map(re.escape, struct_separators_array))
        struct_separators_pattern = f'({struct_separators})'

        found_struct_separators = re.findall(struct_separators_pattern, code)  
        separators_indexes = [m.start() for m in re.finditer(struct_separators_pattern, code)]
        separators_indexes = [index + len(found_struct_separators[i]) for i, index in enumerate(separators_indexes)] # remove the separator length from indexes
        splitted_contents = re.split(struct_separators, code, flags=re.MULTILINE)
        first_chunk_has_usings =  'using' in splitted_contents[0]
        first_chunk_has_namespace = 'namespace' in splitted_contents[0]
        no_content_chunks = int(first_chunk_has_usings or first_chunk_has_namespace)

        if len(found_struct_separators) + no_content_chunks != len(splitted_contents):
            raise Exception('Found class/interface/enum count does not match found contents count')
        
        return found_struct_separators, separators_indexes, splitted_contents
    
    def class_extract_methods_and_props(file_path: str, index_shift_code: int, namespace_name: str, usings: list[str], access_modifier: str, code: str) -> StructureDesc:
        separators = ['public ', 'protected ', 'private ', 'internal ']
        pattern = '|'.join(map(re.escape, separators))
        code_chunks = re.split(pattern, code, flags=re.MULTILINE)
        separator_indexes = [m.start() for m in re.finditer(pattern, code)]

        # Segregate methods from properies        
        methods: list[MethodDesc] = []
        properties: list[PropertyDesc] = []
        chunk_index = -1
        for code_chunk in code_chunks:
            chunk_index += 1
            first_line = code_chunk.split('\n')[0]
            if chunk_index == 0:
                # detect if inherit from an interface
                if CSharpCodeStructureAnalyser.has_interfaces(first_line):
                    class_name = first_line.split(':')[0].strip()
                    interfaces_names = [name.strip() for name in first_line.split(':')[1].split(',')]
                else:
                    class_name = first_line[0].split('(')
                    interfaces_names = []
            else:
                if CSharpCodeStructureAnalyser.is_property(StructureType.Class, first_line):
                    properties.append(PropertyDesc.get_property_desc_from_code(code_chunk))
                else: # is method
                    methods.append(MethodDesc.factory_for_class_code(code_chunk, separator_indexes[chunk_index - 1], code_chunks[chunk_index - 1], class_name))
        
        return StructureDesc(
                    file_path=file_path, 
                    index_shift_code=index_shift_code, 
                    struct_type=StructureType.Class, 
                    namespace_name=namespace_name, 
                    usings=usings, 
                    struct_name=class_name, 
                    access_modifier=access_modifier, 
                    interfaces_names=interfaces_names,
                    base_class_name= None,
                    methods=methods, 
                    properties=properties)

    def interface_extract_methods_and_props(llm, file_path: str, index_shift_code: int, namespace_name: str, usings: list[str], access_modifier: str, code: str) -> StructureDesc:
        # TODO: Implement automatic code parsing for interfaces
        # chains = []
        # prompt = CSharpCodeStructureParser.get_prompt_for_interface_parsing(code)        
        # chain, format_instructions = Llm.get_chain_for_json_output_parser(llm, prompt, StructureDescPydantic, StructureDesc)
        # chains.append(chain)

        # interfaces_summaries = Llm.invoke_parallel_chains({Llm.output_parser_instructions_name: format_instructions}, None, True, *chains)
        # for i in range(len(interfaces_summaries)):
        #     interfaces_summaries[i] = StructureDesc(**interfaces_summaries[i])

        separators = [';' + i*' ' +'\n' for i in range(6)]
        pattern = '|'.join(map(re.escape, separators))
        # for line in re.split(pattern, code, flags=re.MULTILINE):
        #     code_chunks.append(line.strip())
        separator_indexes = [m.start() + len(m.group()) for m in re.finditer(pattern, code)]
        #separator_indexes = [code.rfind('\n', 0, index) for index in separator_indexes] # get the previous NL as separator
        separator_indexes.insert(0, code.find('{') + 2) #add the first line index
        code_lines = code.split('\n')
        # Segregate methods from properies        
        methods: list[MethodDesc] = []
        properties: list[PropertyDesc] = []
        chunk_index = -1
        for code_line in code_lines:            
            code_line = code_line.strip()
            if code_line in ['{', '}', '']:
                continue
            if chunk_index == -1: # first line describe interface signature
                if CSharpCodeStructureAnalyser.has_interfaces(code_line):
                    interface_name = code_line.split(':')[0].strip()
                    interfaces_names = [name.strip() for name in code_line.split(':')[1].split(',')]
                else:
                    interface_name = code_line
                    interfaces_names = []
                chunk_index += 1
                continue
            if CSharpCodeStructureAnalyser.is_property(StructureType.Interface, code_line):
                properties.append(PropertyDesc.get_property_desc_from_code(code_line))
            else: # is method
                methods.append(MethodDesc.factory_for_interface_code(code_line, separator_indexes[chunk_index], interface_name))
            chunk_index += 1

        return StructureDesc(
                    file_path=file_path, 
                    index_shift_code=index_shift_code, 
                    struct_type=StructureType.Interface, 
                    namespace_name=namespace_name, 
                    usings=usings, 
                    struct_name=interface_name, 
                    access_modifier=access_modifier,
                    base_class_name= None, 
                    interfaces_names=interfaces_names, 
                    methods=methods, 
                    properties=properties)

    def is_property(struct_type: StructureType, first_line) -> bool:
        if struct_type == StructureType.Class:
            return first_line.endswith(';') or first_line.endswith('; }') or first_line.endswith(';}')
        elif struct_type == StructureType.Interface:
            return '(' and ')' not in first_line
        
    def is_interface_property(first_line) -> bool:
        return first_line.endswith(';') or first_line.endswith('; }') or first_line.endswith(';}')
    
    def split_method(method_or_prop: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        csharp_splitter = RecursiveCharacterTextSplitter.from_language(language=Language.CSHARP, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return csharp_splitter.create_documents([method_or_prop])
    
    def has_interfaces(first_line: str) -> bool:
        return ':' in first_line
        
    def get_prompt_for_interface_parsing(code: str):      
        prompt = txt.single_line(f"""\
            Hereinafter is the c# code of an interface. The aim is to extract the methods and properties from it:
            {code}.""")        
        return prompt
