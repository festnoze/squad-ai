from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
import re
# internal imports
from models.base_desc import BaseDesc
from models.class_desc import ClassDesc
from models.method_desc import MethodDesc
from models.prop_desc import PropDesc

class CSharpCodeSplit:
    @staticmethod
    def split_code(code: str, chunk_size:int = 8000, chunk_overlap: int = 0) -> BaseDesc:
        found_class_interface_enum, class_interface_enum_contents = CSharpCodeSplit.split_by_class_interface_enum_definition(code)
        last_item_kind: str = found_class_interface_enum[-1][0] # TODO: don't yet handle files with multiple class/interface/enum definitions (can happened, especially in transfert objects files)
        if 'class' in last_item_kind:
            class_desc = CSharpCodeSplit.extract_class_methods_and_props(class_interface_enum_contents[-1])
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
    
    def extract_class_methods_and_props(code: str) -> ClassDesc:
        separators = ['public ', 'protected ', 'private ', 'internal ']
        pattern = '|'.join(map(re.escape, separators))
        chunks = re.split(pattern, code, flags=re.MULTILINE)
        
        # Segregate methods from properies        
        methods: list[MethodDesc] = []
        properties: list[PropDesc] = []
        chunk_index = -1
        for chunk in chunks:
            chunk_index += 1
            first_line = chunk.split('\n')[0]
            if chunk_index == 0:
                # detect if inherit from an interface
                if CSharpCodeSplit.has_interfaces(first_line):
                    class_name = first_line.split(':')[0].strip()
                    interfaces_names = first_line.split(':')[1].split(',')
                else:
                    class_name = first_line[0].split('(')
                    interfaces_names = []
            else:
                if first_line.endswith(';') or first_line.endswith('; }') or first_line.endswith(';}'):
                    properties.append(CSharpCodeSplit.property_desc_from_code(chunk))
                else:
                    summary_str: str = ''
                    attributs_str: str = ''
                    previous_chunk = chunks[chunk_index - 1]
                    previous_chunk_last_double_newline_index = previous_chunk.rfind('\n\n')
                    previous_chunk_last_brace_index = previous_chunk.rfind('}')
                    if previous_chunk_last_double_newline_index > previous_chunk_last_brace_index:
                        previous_chunk_last_part = previous_chunk[previous_chunk_last_double_newline_index:]
                        attributes = CSharpCodeSplit.detect_attributes(previous_chunk_last_part)
                        if len(attributes) > 0:
                            summary = previous_chunk_last_part[:code.index(attributes[0])].split('///')
                        else:
                            summary = previous_chunk_last_part.strip().split('///')
                    methods.append(CSharpCodeSplit.method_desc_from_code(chunk, class_name, summary_str, attributs_str))
        
        print("Le code a été découpé en " + str(len(methods)) + " méthodes et " + str(len(properties)) + " propriétés.")
        return ClassDesc(class_name=class_name, interfaces_names=interfaces_names, methods=methods, properties=properties)

    def detect_attributes(code: str) -> list[str]:
        attributes: list[str] = []
        attribute_pattern = r'\[.*?\]'
        lines = code.split('\n')
        for line in lines:
            if '[' in line:
                line_attributes = re.findall(attribute_pattern, line)
                if len(line_attributes) > 0:
                    attributes.extend(line_attributes)
        return attributes
    
    def property_desc_from_code(first_line) -> PropDesc:
        first_line = first_line.replace('const ', '').replace('readonly ', '').strip()
        is_property = first_line.endswith('; }') or first_line.endswith(';}')
        prop_type = first_line.split(' ')[0]
        if is_property:
            prop_name = first_line.split(' ')[1].split('{')[0].strip()
        else:
            prop_name = first_line.split(' ')[1].split(';')[0].strip()
        return PropDesc(prop_name, prop_type, is_property)
    
    def method_desc_from_code(code: str, class_name: str, summary: str, attributs: list[str]) -> MethodDesc:
        first_line = code.split('\n')[0]

        is_ctor = class_name == first_line.split('(')[0].strip()
        is_task = 'Task<' in first_line
        is_async = 'async ' in first_line
        is_override = 'override ' in first_line
        is_new = 'new ' in first_line
        is_static = 'static ' in first_line
        is_abstract = 'abstract ' in first_line
        is_virtual = 'virtual ' in first_line
        is_sealed = 'sealed ' in first_line

        if not is_ctor:
            if is_async or is_override or is_new or is_static or is_abstract or is_virtual or is_sealed:
                first_line = first_line.replace('override ', '').replace('new ', '').replace('async ','').replace('static ','').replace('abstract ','').replace('virtual ','').replace('sealed ','').strip() 

            if is_async:
                method_return_type = first_line.split(' ')[0].replace('Task<', '').rsplit('>', 1)[0]
            else:
                method_return_type = first_line.split(' ')[0]
            method_name = first_line.split(' ')[1].split('(')[0]

        if is_ctor:
            method_name = class_name
            method_return_type = None

        method_content = code.split('{')[1].rsplit('}', 1)[0]
        return MethodDesc(summary, attributs, method_name, method_return_type, method_content, is_async, is_task, is_ctor, is_static, is_abstract, is_override, is_virtual, is_sealed, is_new)
    
    def split_method(method_or_prop: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        csharp_splitter = RecursiveCharacterTextSplitter.from_language(language=Language.CSHARP, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return csharp_splitter.create_documents([method_or_prop])
    
    def has_interfaces(first_line: str) -> bool:
        return ':' in first_line