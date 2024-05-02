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
        
        found_class_interface_enum, class_interface_enum_contents = CSharpCodeSplit.split_by_class_interface_enum_definition(code)
        last_item_kind: str = found_class_interface_enum[-1][0] # TODO: don't yet handle files with multiple class/interface/enum definitions (can happened, especially in transfert objects files)
        
        if 'class' in last_item_kind:
            class_desc = CSharpCodeSplit.extract_class_methods_and_props(file_path, class_interface_enum_contents[-1])
        elif 'interface' in last_item_kind:
            pass
        elif 'enum' in last_item_kind:
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
        print("Le code a été découpé en " + str(chunk_count) + " morceaux.")
        return class_desc
    
    def split_by_class_interface_enum_definition(code: str) -> tuple[list[str], list[str]]:
        separators = [
            'public class ', 'protected class ', 'private class ', 'internal class ', 
            'public interface ', 'protected interface ', 'private interface ', 'internal interface' , 
            'public enum ', 'protected enum ', 'private enum ', 'internal enum '
            ]
        pattern = '|'.join(map(re.escape, separators))
        
        found_class_interface_enum = re.findall(f'({pattern})', code), 
        class_interface_enum_contents = re.split(pattern, code, flags=re.MULTILINE)

        if len(found_class_interface_enum) + 1 != len(class_interface_enum_contents):
            raise Exception('Found class/interface/enum count does not match the contents count')
        
        return found_class_interface_enum, class_interface_enum_contents
    
    def extract_class_methods_and_props(file_path: str, code: str) -> ClassDesc:
        separators = ['public ', 'protected ', 'private ', 'internal ']
        pattern = '|'.join(map(re.escape, separators))
        code_chunks = re.split(pattern, code, flags=re.MULTILINE)
        
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
        
        print("Le code a été découpé en " + str(len(methods)) + " méthodes et " + str(len(properties)) + " propriétés.")
        return ClassDesc(file_path=file_path, class_name=class_name, interfaces_names=interfaces_names, methods=methods, properties=properties)

    def is_property(first_line) -> bool:
        return first_line.endswith(';') or first_line.endswith('; }') or first_line.endswith(';}')
    
    def split_method(method_or_prop: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        csharp_splitter = RecursiveCharacterTextSplitter.from_language(language=Language.CSHARP, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return csharp_splitter.create_documents([method_or_prop])
    
    def has_interfaces(first_line: str) -> bool:
        return ':' in first_line