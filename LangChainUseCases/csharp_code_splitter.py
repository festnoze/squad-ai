from textwrap import dedent
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
import re
# internal imports
from helpers.c_sharp_helpers import CSharpXMLDocumentation
from helpers.llm_helper import Llm
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
    
    def generate_all_methods_summaries(llm: BaseChatModel, class_desc: ClassDesc, with_json_output_parsing: bool):
        # Generate methods summaries
        methods_summaries_prompts = []
        for method in class_desc.methods:
            method_summary = CSharpCodeSplit.generate_method_summary_prompt(llm, method)
            methods_summaries_prompts.append(method_summary)

        methods_summaries = Llm.invoke_parallel_prompts(llm, *methods_summaries_prompts)
        for method, method_summary in zip(class_desc.methods, methods_summaries):
            method.generated_summary = method_summary

        # Generate parameters summaries for all methods
        prompts_or_chains = []
        format_instructions = ''
        for method in class_desc.methods:
            prompt, json_formatting_spec_prompt = CSharpCodeSplit.get_prompt_for_parameters_summaries(method, method_summary)        
            if with_json_output_parsing:
                prompt_or_chain, format_instructions = Llm.get_chain_for_json_output_parser(llm, prompt, MethodParametersDocumentationPydantic, MethodParametersDocumentation)
            else:
                prompt_or_chain = prompt + json_formatting_spec_prompt
            prompts_or_chains.append(prompt_or_chain)

        if with_json_output_parsing:
            methods_parameters_summaries = Llm.invoke_parallel_chains({Llm.output_parser_instructions_name: format_instructions}, *prompts_or_chains)
            for i in range(len(methods_parameters_summaries)):
                methods_parameters_summaries[i] = MethodParametersDocumentation(**methods_parameters_summaries[i])
        else:
            methods_parameters_summaries = Llm.invoke_parallel_prompts(llm, *prompts_or_chains)

        if with_json_output_parsing:
            for method, method_params_summaries in zip(class_desc.methods, methods_parameters_summaries):
                method.generated_parameters_summaries = method_params_summaries
        else:            
            for method, method_params_summaries in zip(class_desc.methods, methods_parameters_summaries):
                method_params_summaries_str = Llm.get_llm_answer_content(method_params_summaries)
                method_params_summaries_str = Llm.extract_json_from_llm_response(method_params_summaries_str)
                method_params_summaries_built = MethodParametersDocumentation.from_json(method_params_summaries_str)
                method.generated_parameters_summaries = method_params_summaries_built


        # Generate method return summaries for all methods
        prompts = []
        for method in [met for met in class_desc.methods if met.has_return_type()]:
            prompts.append(CSharpCodeSplit.get_prompt_for_method_return_summary(llm, method))
        methods_return_summaries_only = Llm.invoke_parallel_prompts(llm, *prompts)
        # Apply return method summary only to methods with a return type
        return_index = 0
        for i in range(len(class_desc.methods)):
            if class_desc.methods[i].has_return_type():
                class_desc.methods[i].generated_return_summary = methods_return_summaries_only[return_index]
                return_index += 1

        # Assign to all methods a generated summary including method description, parameters description, and return type description
        for i in range(len(class_desc.methods)):
            method = class_desc.methods[i]
            method.generated_xml_summary = CSharpXMLDocumentation(method.generated_summary, method.generated_parameters_summaries, method.generated_return_summary, None) #method.example


    ctor_txt = "Take into account that this method is a constructor for the containing class of the same name."
        
    def generate_method_summary_prompt(llm: BaseChatModel, method: MethodDesc) -> str:        
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
        return prompt

        # TODO: see how to rather use code_chunks from method_desc for big methods
        # docs = Summarize.split_text(llm, text, max_tokens)
        # chain = Summarize.splitting_chain(llm)
        # method_summary = Summarize.split_prompt_and_invoke(llm, prompt, 8000)
        # return method_summary
    
    def get_prompt_for_parameters_summaries(method: MethodDesc, method_summary: str):      
        method_params_str = ', '.join([item.to_str() for item in method.params])

        # Base prompt w/o json output format spec. (used alone in case of further use of an output parser to convert the LLM response to the specified pydantic json object)
        method_params_summaries_prompt = txt.single_line(f"""\
            The list of parameters is: '{method_params_str}'. We have an existing method named: '{method.method_name}', 
            {CSharpCodeSplit.ctor_txt if method.is_ctor else ""} for context, the method purpose is: '{method_summary}'.
            Generate a description for each parameter of the following C# method.""")
        
        # Prompt extension to specify the awaited json output format (used when no output parser is defined)
        json_formatting_spec_prompt = txt.single_line(f"""
            The awaited output should be a json array, with one item by parameter, each item having two keys: 
            - 'param_name': containing the parameter name, 
            - and 'param_desc': containing the description that you have generated of the parameter.""")
        
        return method_params_summaries_prompt, json_formatting_spec_prompt
            
    def get_prompt_for_method_return_summary(llm: BaseChatModel, method: MethodDesc) -> str:
        params_list = txt.get_prop_or_key(method.generated_parameters_summaries, 'params_list')
        params_list_str = ' ; '.join([str(item) for item in params_list])
        prompt = txt.single_line(f"""\
            Create a description of the return value of the following C# method.
            Instructions: You always begin with: 'Returns ' then generate a description of the return value. The description must be very short and synthetic (less than 15 words)
            The method name is: '{method.method_name}', {CSharpCodeSplit.ctor_txt if method.is_ctor else ""} and to help you understand the purpose of the method, method summary is: '{method.generated_summary}'.
            The list of parameters is: '{params_list_str}'.""")
        return prompt
