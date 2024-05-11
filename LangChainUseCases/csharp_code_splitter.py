from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
import re
# internal imports
from helpers.file_helper import file
from models.base_desc import BaseDesc
from models.class_desc import ClassDesc
from models.method_desc import MethodDesc
from models.prop_desc import PropertyDesc
from summarize import Summarize

class CSharpCodeSplit:
    @staticmethod
    def get_code_structure(file_path: str, chunk_size:int = 8000, chunk_overlap: int = 0) -> BaseDesc:
        code = file.get_as_str(file_path)
        
        found_struct_separators, splitted_struct_contents = CSharpCodeSplit.split_by_class_interface_enum_definition(code)
        struct_type: str = found_struct_separators[-1].split()[-1] # TODO: don't yet handle files with multiple class/interface/enum definitions (can happened, especially in transfert objects files)
        access_modifier = found_struct_separators[-1].split()[0]
        first_chunk_has_usings =  'using' in splitted_struct_contents[0]
        first_chunk_has_namespace = 'namespace' in splitted_struct_contents[0]
        
        if first_chunk_has_namespace:
            namespace_name = re.search(r'namespace\s+([\w.]+)[\s;]*', splitted_struct_contents[0]).group(1)
        if first_chunk_has_usings:
            usings = re.findall(r'using\s+([\w.]+)[\s;]*', splitted_struct_contents[0]) 

        if struct_type == 'class':
            class_desc = CSharpCodeSplit.extract_class_methods_and_props(file_path, namespace_name, usings, access_modifier, struct_type, splitted_struct_contents[-1])
        elif struct_type == 'interface':
            pass
        elif struct_type == 'enum':
            pass

        # split each method into chunks adapted to the LLM context window size
        chunk_count = 0
        for method in class_desc.methods:
            method_chunks = CSharpCodeSplit.split_method(method.code, chunk_size, chunk_overlap)
            if (len(method_chunks) < 2):
                method.code_chunks = None
            else:
                method.code_chunks = method_chunks
            chunk_count += len(method_chunks)
        return class_desc
    
    def split_by_class_interface_enum_definition(code: str) -> tuple[list[str], list[str]]:
        struct_separators_array = [
            'public class ', 'protected class ', 'private class ', 'internal class ', 
            'public interface ', 'protected interface ', 'private interface ', 'internal interface' , 
            'public enum ', 'protected enum ', 'private enum ', 'internal enum '
            ]
        struct_separators = '|'.join(map(re.escape, struct_separators_array))
        struct_separators_pattern = f'({struct_separators})'

        found_struct_separators = re.findall(struct_separators_pattern, code)  
        splitted_contents = re.split(struct_separators, code, flags=re.MULTILINE)
        first_chunk_has_usings =  'using' in splitted_contents[0]
        first_chunk_has_namespace = 'namespace' in splitted_contents[0]
        no_content_chunks = int(first_chunk_has_usings or first_chunk_has_namespace)

        if len(found_struct_separators) + no_content_chunks != len(splitted_contents):
            raise Exception('Found class/interface/enum count does not match the contents count')
        
        return found_struct_separators, splitted_contents
    
    def extract_class_methods_and_props(file_path: str, namespace_name: str, usings: list[str], access_modifier: str, structure_type: str, code: str) -> ClassDesc:
        separators = ['public ', 'protected ', 'private ', 'internal ']
        pattern = '|'.join(map(re.escape, separators))
        code_chunks = re.split(pattern, code, flags=re.MULTILINE)
        access_modifier = access_modifier
        structure_type = structure_type
        # Segregate methods from properies        
        methods: list[MethodDesc] = []
        properties: list[PropertyDesc] = []
        chunk_index = -1
        for code_chunk in code_chunks:
            chunk_index += 1
            first_line = code_chunk.split('\n')[0]
            if chunk_index == 0:
                # detect if inherit from an interface
                if CSharpCodeSplit.has_interfaces(first_line):
                    class_name = first_line.split(':')[0].strip()
                    interfaces_names = first_line.split(':')[1].split(',')
                else:
                    class_name = first_line[0].split('(')
                    interfaces_names = []
            else:
                if CSharpCodeSplit.is_property(first_line):
                    properties.append(PropertyDesc.get_property_desc_from_code(code_chunk))
                else: # is method
                    methods.append(MethodDesc.get_method_desc_from_code(code_chunk, code_chunks[chunk_index - 1], class_name))
        return ClassDesc(file_path=file_path, namespace_name=namespace_name, usings=usings, class_name=class_name, access_modifier=access_modifier, structure_type=structure_type, interfaces_names=interfaces_names, methods=methods, properties=properties)

    def is_property(first_line) -> bool:
        return first_line.endswith(';') or first_line.endswith('; }') or first_line.endswith(';}')
    
    def split_method(method_or_prop: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        csharp_splitter = RecursiveCharacterTextSplitter.from_language(language=Language.CSHARP, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return csharp_splitter.create_documents([method_or_prop])
    
    def has_interfaces(first_line: str) -> bool:
        return ':' in first_line