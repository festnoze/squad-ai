from textwrap import dedent
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from langchain_core.language_models import BaseChatModel
import re
# internal imports
from helpers.agents_workflows import invoke_llm_with_json_output_parser
from helpers.c_sharp_helpers import CSharpXMLDocumentation
from helpers.txt_helper import txt
from models.base_desc import BaseDesc
from models.class_desc import ClassDesc
from models.method_desc import MethodDesc
from models.param_doc import ParameterDocumentation
from models.params_doc import MethodParametersDocumentation, MethodParametersDocumentationPydantic
from models.prop_desc import PropertyDesc
from summarize import Summarize

class CSharpCodeSplit:
    @staticmethod
    def extract_code_struct(llm: BaseChatModel, file_path: str, code: str, chunk_size:int = 8000, chunk_overlap: int = 0) -> BaseDesc:
        found_struct_separators, splitted_struct_contents, separator_indexes = CSharpCodeSplit.split_by_class_interface_enum_definition(code)
         # TODO: don't yet handle files with multiple class/interface/enum definitions (can happened, especially in transfert objects files)
        if len(splitted_struct_contents) > 2:
            raise Exception('Multiple class/interface/enum definitions per file are not yet supported')
        
        first_chunk_has_usings =  'using' in splitted_struct_contents[0]
        first_chunk_has_namespace = 'namespace' in splitted_struct_contents[0]
        access_modifier = found_struct_separators[-1].split()[0]
        struct_type: str = found_struct_separators[-1].split()[-1]

        if first_chunk_has_namespace:
            namespace_name = re.search(r'namespace\s+([\w.]+)[\s;]*', splitted_struct_contents[0]).group(1)
        if first_chunk_has_usings:
            usings = re.findall(r'using\s+([\w.]+)[\s;]*', splitted_struct_contents[0]) 

        if struct_type == 'class':
            class_desc = CSharpCodeSplit.extract_class_methods_and_props(file_path, separator_indexes[0], namespace_name, usings, access_modifier, struct_type, splitted_struct_contents[-1])
        elif struct_type == 'interface':
            pass
        elif struct_type == 'enum':
            pass

        # split each method into chunks adapted to the LLM context window size
        CSharpCodeSplit.split_class_methods_and_add_to_class_desc(class_desc, chunk_size, chunk_overlap)
        
        return class_desc
    
    def split_class_methods_and_add_to_class_desc(class_desc: ClassDesc, chunk_size:int = 8000, chunk_overlap: int = 0):
        # split each method into chunks adapted to the LLM context window size
        chunk_count = 0
        for method in class_desc.methods:
            method_chunks = CSharpCodeSplit.split_method(method.code, chunk_size, chunk_overlap)
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
        separator_indexes = [m.start() for m in re.finditer(struct_separators_pattern, code)]
        splitted_contents = re.split(struct_separators, code, flags=re.MULTILINE)
        first_chunk_has_usings =  'using' in splitted_contents[0]
        first_chunk_has_namespace = 'namespace' in splitted_contents[0]
        no_content_chunks = int(first_chunk_has_usings or first_chunk_has_namespace)

        if len(found_struct_separators) + no_content_chunks != len(splitted_contents):
            raise Exception('Found class/interface/enum count does not match the contents count')
        
        return found_struct_separators, splitted_contents, separator_indexes
    
    def extract_class_methods_and_props(file_path: str, index_shift_code: int, namespace_name: str, usings: list[str], access_modifier: str, structure_type: str, code: str) -> ClassDesc:
        separators = ['public ', 'protected ', 'private ', 'internal ']
        pattern = '|'.join(map(re.escape, separators))
        code_chunks = re.split(pattern, code, flags=re.MULTILINE)
        separator_indexes = [m.start() + len(m.group()) for m in re.finditer(pattern, code)]
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
                    interfaces_names = [name.strip() for name in first_line.split(':')[1].split(',')]
                else:
                    class_name = first_line[0].split('(')
                    interfaces_names = []
            else:
                if CSharpCodeSplit.is_property(first_line):
                    properties.append(PropertyDesc.get_property_desc_from_code(code_chunk))
                else: # is method
                    methods.append(MethodDesc.factory_from_code(code_chunk, separator_indexes[chunk_index - 1], code_chunks[chunk_index - 1], class_name))
        return ClassDesc(file_path=file_path, index_shift_code=index_shift_code, namespace_name=namespace_name, usings=usings, class_name=class_name, access_modifier=access_modifier, structure_type=structure_type, interfaces_names=interfaces_names, methods=methods, properties=properties)

    def is_property(first_line) -> bool:
        return first_line.endswith(';') or first_line.endswith('; }') or first_line.endswith(';}')
    
    def split_method(method_or_prop: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        csharp_splitter = RecursiveCharacterTextSplitter.from_language(language=Language.CSHARP, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return csharp_splitter.create_documents([method_or_prop])
    
    def has_interfaces(first_line: str) -> bool:
        return ':' in first_line
    
    def generate_all_methods_summaries(llm: BaseChatModel, class_desc: ClassDesc, separate_output_formating: bool):
        for method in class_desc.methods:
            method_summary = CSharpCodeSplit.generate_method_summary(llm, method)
            method_params_summaries = CSharpCodeSplit.generate_parameters_summaries(llm, method, method_summary, separate_output_formating)
            method_return_summary = CSharpCodeSplit.generate_method_return_summary(llm, method, method_summary, method_params_summaries) if not method.is_ctor else None  
            method.generated_summary = CSharpXMLDocumentation.get_xml(method_summary, method_params_summaries, method_return_summary, None) #method.example

    ctor_txt = "Take into account that this method is a constructor for the containing class of the same name."
        
    def generate_method_summary(llm: BaseChatModel, method: MethodDesc) -> str:        
        output_format = txt.single_line(f"""
                Respect the following format: Your answer must have a direct, conscise and factual style. 
                Your answer must always begin by an action verb, (like: 'Get', 'Retrieve', 'Update', 'Check', etc ...) to describe the aim of the method, 
                then possibly followed by any needed precisions, like: conditions, infos about concerned data, or anything else.
                For example: 'Retrieve the last message for a specified user' is a good formated answer, where as:
                'This method retrieves the last message by user ID' is not formated correctly.""")
            
        prompt = txt.single_line(f"""
                Analyse method name and the method code to produce a summary of it's functionnal purpose and behavior 
                without any mention to the method name or any technicalities, nor any mention whether it's asynchronous. 
                {CSharpCodeSplit.ctor_txt if method.is_ctor else ""} {output_format}             
                The method name is: '{method.method_name}' and its full code is: """)
        prompt += '\n' + method.code

        method_summary = Summarize.split_and_invoke(llm, prompt, 15000)
        return method_summary
    
    def generate_parameters_summaries(llm: BaseChatModel, method: MethodDesc, method_summary: str, separate_output_formating: bool) -> MethodParametersDocumentation:      
        method_params_str = ', '.join([item.to_str() for item in method.params])
        # # directly ask LLM to create the json object
        # method_params_summaries_prompt = f"Create a description of each parameter of the following C# method. The awaited output should be a json array, with two keys: param_name, and param_desc. The list of parameters is (a parameter consist of a type followed by a name with comma as separator): '{method_params_str}'. The containing method name is: '{method.method_name}', {ctor_txt} and to help you understand the purpose of the method, method summary is: '{method_summary}'."
        # method_params_summaries_response = llm.invoke(method_params_summaries_prompt)
        
        # Use a json output parser to convert the LLM output to the specified pydantic json object
        method_params_summaries_prompt = txt.single_line(f"""\
            The list of parameters is: '{method_params_str}'. We have an existing method named: '{method.method_name}', 
            {CSharpCodeSplit.ctor_txt if method.is_ctor else ""} for context, the method purpose is: '{method_summary}'.
            Generate a description for each parameter of the following C# method.""")
        
        specify_json_formatting_prompt = txt.single_line(f"""
            The awaited output should be a json array, with one item by parameter, each item having two keys: 
            - 'param_name': containing the parameter name, 
            - and 'param_desc': containing the description that you have generated of the parameter.""")
        
        if separate_output_formating:
            # Use output parser to get the awaited json format rather than describing it into the prompt 
            method_params_summaries = invoke_llm_with_json_output_parser(llm, method_params_summaries_prompt, MethodParametersDocumentationPydantic, MethodParametersDocumentation)
        else:
            # Use direct asking for params description + json parsing to LLM
            method_params_summaries_response = llm.invoke(method_params_summaries_prompt + specify_json_formatting_prompt)
            method_params_summaries_str = txt.get_llm_answer_content(method_params_summaries_response)
            method_params_summaries = MethodParametersDocumentation.from_json(method_params_summaries_str)
        
        return method_params_summaries
    
    def generate_method_return_summary(llm: BaseChatModel, method: MethodDesc, method_summary: str, method_params_summaries: MethodParametersDocumentation) -> str:
        # directly ask LLM to create the json object
        prompt = txt.single_line(f"""\
            Create a description of the return value of the following C# method.
            Instructions: You always begin with: 'Returns ' then generate a description of the return value. The description must be very short and synthetic (less than 15 words)
            The method name is: '{method.method_name}', {CSharpCodeSplit.ctor_txt if method.is_ctor else ""} and to help you understand the purpose of the method, method summary is: '{method_summary}'.
            The list of parameters is: '{' ; '.join([str(item) for item in method_params_summaries.params_list])}'.""")
        method_return_summary_response = llm.invoke(prompt)
        return txt.get_llm_answer_content(method_return_summary_response)
